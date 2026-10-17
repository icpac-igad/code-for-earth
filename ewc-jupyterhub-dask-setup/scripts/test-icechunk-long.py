"""Longer Icechunk workload on the EWC cluster - enough runtime to watch the
Dask dashboard.

Extends test-icechunk-write.py (which proved the plumbing works) into something
that runs for minutes rather than seconds:

  Phase 1  write N days at 0.25 deg, one commit per day  -> steady write load
  Phase 2  read the whole store back and reduce it       -> many small reads
  Phase 3  rolling statistics over time                  -> inter-worker shuffle

Phase 3 is the interesting one to watch: rolling windows force workers to
exchange chunks with each other rather than working independently, so it
exercises the worker-to-worker port range in the dask-internal security group.
If that were missing, phases 1-2 would pass and phase 3 would hang.

Prerequisites (client needs credentials too, not just workers):

    export AWS_ENDPOINT_URL=https://object-store.os-api.<region>.ecmwf.int
    export AWS_DEFAULT_REGION=RegionOne
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...

Run:

    /opt/mamba/envs/dask/bin/python test-icechunk-long.py --days 10
    /opt/mamba/envs/dask/bin/python test-icechunk-long.py --days 30 --cleanup
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

# 0.25 degree global, matching the ECMWF IFS operational grid.
NLAT, NLON = 721, 1440
STEPS_PER_DAY = 24


def day_dataset(date, nlat=NLAT, nlon=NLON, nsteps=STEPS_PER_DAY):
    times = pd.date_range(date, periods=nsteps, freq="1h")
    shape = (nsteps, nlat, nlon)
    chunks = (1, nlat, nlon)                 # one task per lead time
    return xr.Dataset(
        {
            "t2m": (("time", "lat", "lon"),
                    da.random.normal(288.0, 8.0, shape, chunks=chunks).astype("f4"),
                    {"units": "K"}),
            "tp": (("time", "lat", "lon"),
                   da.random.gamma(2.0, 1.5, shape, chunks=chunks).astype("f4"),
                   {"units": "mm"}),
        },
        coords={
            "time": times,
            "lat": np.linspace(90, -90, nlat, dtype="f4"),
            "lon": np.linspace(0, 359.75, nlon, dtype="f4"),
        },
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--start", default="2025-07-01")
    ap.add_argument("--bucket", default="<your-bucket>")
    ap.add_argument("--prefix", default="long-test")
    ap.add_argument("--scheduler", default=os.environ.get(
        "DASK_SCHEDULER_ADDRESS", "tcp://127.0.0.1:8786"))
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()

    import icechunk as ic
    from icechunk.xarray import to_icechunk
    from dask.distributed import Client

    client = Client(args.scheduler)
    info = client.scheduler_info()["workers"]
    nthreads = sum(w["nthreads"] for w in info.values())

    user = os.environ.get("JUPYTERHUB_USER", "<user>")
    print(f"cluster : {len(info)} workers, {nthreads} threads")
    print(f"dashboard: https://hub-a.example.org"
          f"/user/{user}/proxy/8787/status")
    print(f"           (or the raw link: {client.dashboard_link})\n")

    storage = ic.s3_storage(
        bucket=args.bucket, prefix=args.prefix, region=REGION,
        endpoint_url=ENDPOINT, from_env=True, force_path_style=True)
    repo = ic.Repository.open_or_create(storage)

    dates = pd.date_range(args.start, periods=args.days, freq="1D")
    per_day_mb = 2 * STEPS_PER_DAY * NLAT * NLON * 4 / 1e6
    print(f"PHASE 1: writing {args.days} days x {per_day_mb:.0f} MB "
          f"= {args.days * per_day_mb / 1000:.1f} GB, one commit per day")

    t_start = time.time()
    for i, d in enumerate(dates):
        ds = day_dataset(d)
        session = repo.writable_session("main")
        t0 = time.time()
        # append_dim on all but the first day, so the store grows along time
        # rather than being overwritten.
        if i == 0:
            to_icechunk(ds, session, mode="w")
        else:
            to_icechunk(ds, session, append_dim="time")
        snap = session.commit(f"day {d:%Y-%m-%d}")
        dt = time.time() - t0
        print(f"  [{i+1:>3}/{args.days}] {d:%Y-%m-%d}  {dt:5.1f}s  "
              f"{per_day_mb/dt:5.0f} MB/s  snapshot {snap[:12]}")

    write_wall = time.time() - t_start
    total_gb = args.days * per_day_mb / 1000
    print(f"\nwrote {total_gb:.1f} GB in {write_wall:.0f}s "
          f"({total_gb*1000/write_wall:.0f} MB/s aggregate)")

    # --- phase 2: full-store reduction ---------------------------------------
    ro = repo.readonly_session("main")
    ds = xr.open_zarr(ro.store, consolidated=False, zarr_format=3, chunks={})
    n_chunks = ds["t2m"].data.npartitions + ds["tp"].data.npartitions
    print(f"\nPHASE 2: reducing whole store, {dict(ds.sizes)}, "
          f"{n_chunks} chunks to read")

    t0 = time.time()
    means = client.compute([ds["t2m"].mean(), ds["tp"].mean()], sync=True)
    dt = time.time() - t0
    print(f"  mean t2m={float(means[0]):.2f} K, tp={float(means[1]):.3f} mm "
          f"in {dt:.0f}s ({total_gb*1000/dt:.0f} MB/s read)")

    # --- phase 3: rolling stats (forces worker-to-worker traffic) ------------
    print(f"\nPHASE 3: 24h rolling std over time - watch the dashboard task "
          f"stream for inter-worker transfer")
    # Dask requires the rolling window to fit inside a chunk, and the store is
    # written one time-step per chunk (24 per day). Rechunking to wider time
    # blocks and narrower spatial ones is what forces the cross-worker
    # transfer this phase is meant to exercise.
    t0 = time.time()
    rechunked = ds["t2m"].chunk({"time": 48, "lat": 361, "lon": 720})
    roll = rechunked.rolling(time=24, min_periods=1).std().mean(dim=("lat", "lon"))
    out = client.compute(roll, sync=True)
    dt = time.time() - t0
    print(f"  {len(out)} rolling values in {dt:.0f}s, "
          f"mean spread {float(out.mean()):.3f} K")

    hosts = sorted(set(client.run(socket.gethostname).values()))
    print(f"\nexecuted on: {', '.join(hosts)}")
    print(f"total wall time: {time.time() - t_start:.0f}s")

    if args.cleanup:
        import s3fs
        fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": ENDPOINT})
        fs.rm(f"{args.bucket}/{args.prefix}", recursive=True)
        print(f"cleaned up s3://{args.bucket}/{args.prefix}")

    client.close()


if __name__ == "__main__":
    main()
