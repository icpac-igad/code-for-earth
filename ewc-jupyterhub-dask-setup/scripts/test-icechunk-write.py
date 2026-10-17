"""Distributed Icechunk write test against the EWC object store.

Writes a small *realized* (materialized) dataset for one date from the Dask
cluster, commits it, and reads it back. Unlike a virtual/reference store this
actually puts chunks in the bucket, so it exercises the whole path:

    notebook -> dask workers -> S3 (Ceph RadosGW) -> icechunk commit

The commit is the interesting part. Icechunk uses conditional writes
(If-None-Match) so concurrent commits cannot clobber each other. AWS S3
supports this; Ceph RadosGW support is version dependent. If the commit fails
here, Icechunk cannot safely serialise concurrent writers on this backend --
find that out now, not after building a pipeline on it.

Run from a JupyterHub notebook terminal on gateway 1:

    python test-icechunk-write.py --date 2026-07-29
    python test-icechunk-write.py --date 2026-07-29 --cleanup

Exit code 0 = all PASS, 1 = any FAIL.
"""
import argparse
import os
import socket
import time

import numpy as np
import pandas as pd
import xarray as xr
import dask.array as da

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL",
                          "https://object-store.os-api.<region>.ecmwf.int")
REGION = os.environ.get("AWS_DEFAULT_REGION", "RegionOne")
FAILURES = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def build_dataset(date, nlat=451, nlon=900, nsteps=8):
    """A day of synthetic 0.4-degree-ish fields, chunked one chunk per step.

    Shape mirrors the ECMWF 0.4 grid used elsewhere in the GIK work so the
    chunk sizes and task counts are representative rather than toy-sized.
    """
    times = pd.date_range(date, periods=nsteps, freq="3h")
    shape = (nsteps, nlat, nlon)
    chunks = (1, nlat, nlon)          # one task per lead time
    t2m = da.random.normal(288.0, 8.0, size=shape, chunks=chunks).astype("f4")
    tp = da.random.gamma(2.0, 1.5, size=shape, chunks=chunks).astype("f4")
    return xr.Dataset(
        {
            "t2m": (("time", "lat", "lon"), t2m, {"units": "K"}),
            "tp": (("time", "lat", "lon"), tp, {"units": "mm"}),
        },
        coords={
            "time": times,
            "lat": np.linspace(90, -90, nlat, dtype="f4"),
            "lon": np.linspace(0, 359.6, nlon, dtype="f4"),
        },
        attrs={"source": "test-icechunk-write.py", "date": str(date)},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="e.g. 2026-07-29")
    ap.add_argument("--bucket", default="<your-bucket>")
    ap.add_argument("--prefix", default=None,
                    help="default: realized-test/<date>")
    ap.add_argument("--scheduler", default=os.environ.get(
        "DASK_SCHEDULER_ADDRESS", "tcp://127.0.0.1:8786"))
    ap.add_argument("--cleanup", action="store_true",
                    help="delete the store's objects afterwards")
    args = ap.parse_args()
    prefix = args.prefix or f"realized-test/{args.date}"

    import icechunk as ic
    from icechunk.xarray import to_icechunk
    from dask.distributed import Client

    client = Client(args.scheduler)
    info = client.scheduler_info()["workers"]
    print(f"cluster: {len(info)} workers, "
          f"{sum(w['nthreads'] for w in info.values())} threads")

    # Credentials must be present on the WORKERS, not just here - the workers
    # are what talk to S3. The file is 0600 root, so check the environment.
    worker_creds = client.run(lambda: bool(os.environ.get("AWS_ACCESS_KEY_ID")))
    check("all workers have S3 credentials", all(worker_creds.values()),
          f"{sum(worker_creds.values())}/{len(worker_creds)}")

    ds = build_dataset(args.date)
    nbytes = sum(v.nbytes for v in ds.data_vars.values())
    print(f"\ndataset {dict(ds.sizes)} -> {nbytes/1e6:.0f} MB realized, "
          f"{sum(len(v.chunks[0]) for v in ds.data_vars.values())} write tasks")

    storage = ic.s3_storage(
        bucket=args.bucket, prefix=prefix, region=REGION,
        endpoint_url=ENDPOINT, from_env=True, force_path_style=True)

    repo = ic.Repository.open_or_create(storage)
    check("repository open_or_create on Ceph RGW", True, f"s3://{args.bucket}/{prefix}")

    # --- distributed write ---------------------------------------------------
    # to_icechunk() is the distributed-safe writer: workers write chunks, then
    # their change-sets are merged back into this session for a single commit.
    # Plain ds.to_zarr(session.store) is NOT safe from multiple processes.
    session = repo.writable_session("main")
    t0 = time.time()
    to_icechunk(ds, session, mode="w")
    write_wall = time.time() - t0
    print(f"chunks written in {write_wall:.1f}s ({nbytes/1e6/write_wall:.0f} MB/s)")

    # --- the commit: this is what needs conditional writes -------------------
    try:
        snap = session.commit(f"realized test write for {args.date}")
        check("commit succeeded (conditional writes supported)", bool(snap),
              f"snapshot {snap}")
    except Exception as e:
        check("commit succeeded (conditional writes supported)", False,
              f"{type(e).__name__}: {e}")
        print("\n  -> If this mentions If-None-Match / precondition / not "
              "implemented, Ceph RGW lacks conditional-write support.\n"
              "     Options: single-writer discipline, or plain Zarr on S3.")
        raise SystemExit(1)

    # --- read back through the cluster ---------------------------------------
    ro = repo.readonly_session("main")
    back = xr.open_zarr(ro.store, consolidated=False, zarr_format=3, chunks={})
    check("readback has expected variables",
          set(back.data_vars) == {"t2m", "tp"}, str(list(back.data_vars)))
    check("readback shape matches", dict(back.sizes) == dict(ds.sizes),
          str(dict(back.sizes)))

    mean_t2m = float(back["t2m"].mean().compute())
    check("t2m round-trips plausibly (250-320 K)", 250 < mean_t2m < 320,
          f"mean={mean_t2m:.2f} K")

    hosts = set(client.run(socket.gethostname).values())
    check("work ran on worker VMs, not locally",
          socket.gethostname() not in hosts, f"{len(hosts)} workers")

    # --- second commit: does concurrent-safety actually hold? ----------------
    # A second session started BEFORE the first commit should be rejected on
    # commit. That rejection is the guarantee; if it silently succeeds, commits
    # are not serialised and concurrent writers can lose data.
    s1 = repo.writable_session("main")
    s2 = repo.writable_session("main")
    import zarr
    zarr.open_group(store=s1.store, mode="a").create_array(
        "conflict_a", shape=(4,), dtype="i4")
    zarr.open_group(store=s2.store, mode="a").create_array(
        "conflict_b", shape=(4,), dtype="i4")
    s1.commit("writer 1")
    try:
        s2.commit("writer 2")
        check("stale session rejected (commits serialised)", False,
              "second commit succeeded - concurrent writes are NOT safe")
    except Exception as e:
        check("stale session rejected (commits serialised)", True,
              type(e).__name__)

    if args.cleanup:
        import s3fs
        fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": ENDPOINT})
        fs.rm(f"{args.bucket}/{prefix}", recursive=True)
        print(f"\ncleaned up s3://{args.bucket}/{prefix}")

    client.close()
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    raise SystemExit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
