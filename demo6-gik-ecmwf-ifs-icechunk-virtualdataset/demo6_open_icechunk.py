#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "icechunk>=2.1",
#   "zarr>=3.2",
#   "xarray>=2025.1",
#   "numpy",
#   "gribberish>=1.4",
#   "s3fs",
#   "matplotlib",
# ]
# ///
"""
demo6 — open the PUBLISHED ECMWF IFS ensemble Icechunk store (source.coop),
        anonymously, and read total precipitation for ONE forecast date.

This is the payoff of Component 1. Demo 1 built a GIK manifest from one GRIB's
`.index`; Demo 2 byte-range-read one message out of one GRIB. This demo opens
the *whole archive* — 51 init dates x 51 members x 85 steps — as a single,
analysis-ready Icechunk virtual dataset, with ZERO credentials.

What "virtual" means here:
    The store's metadata (repo pointer + snapshots + manifests) lives on
    source.coop. It holds NO data bytes. Every chunk is a *virtual reference*
    into the public `s3://ecmwf-forecasts/` GRIB archive on AWS. When you slice
    a variable, icechunk resolves the reference, does an anonymous byte-range
    GET against ecmwf-forecasts, and decodes it through the `gribberish` Zarr v3
    codec. `xarray` reports the store as ~168 TB, but you only ever move the few
    hundred KB of the field you actually touch.

What this demo reads:
    total precipitation (`tp`) for one forecast init date, one member, one
    accumulation window -- the flood-relevant field Component 2 builds on. `tp`
    is ACCUMULATED from step 0, so `tp` at step=24 IS the 0-24 h total (mm after
    a *1000 conversion from metres). Step 0 is all-zero by definition.

Run:
    uv run demo6_open_icechunk.py       # uv reads the inline metadata above
                                        # and installs deps in an ephemeral env

    NOT  `uv run python demo6_open_icechunk.py`  — putting `python` between
    `uv run` and the script name bypasses the PEP 723 metadata and uses
    whatever `python` is on PATH, which may be missing icechunk / gribberish.

    Run it WITHOUT any AWS_* env vars set (`from_env=False` ignores them anyway,
    but the point is that no credentials are needed at all).

Output:
    ./example.png   -- a global map of the selected tp field.

Store reference (endpoint, groups, gotchas, and an all-era smoke test):
    see this folder's README.md.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

try:
    import numpy as np
    import icechunk
    import xarray as xr
    import gribberish.zarr  # noqa: F401  -- registers the "gribberish" Zarr v3 codec
except ImportError as e:
    sys.exit(
        f"\n!! {e.name} not importable.\n"
        f"   Run this script with `uv run demo6_open_icechunk.py` (no `python`\n"
        f"   in between) so uv reads the PEP 723 metadata at the top and installs\n"
        f"   icechunk + zarr + xarray + gribberish + s3fs in an ephemeral env.\n"
        f"   If you cannot use uv, install manually:\n"
        f"       pip install icechunk zarr xarray numpy gribberish s3fs matplotlib")

# ---- The published store (all public, all anonymous) ----------------------
ENDPOINT = "https://data.source.coop"
BUCKET   = "e4drr-project"
PREFIX   = "forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd"
CONTAINER = "s3://ecmwf-forecasts/"   # where the virtual chunks physically live
GROUP    = "50r1/00z"                 # current IFS schema era (see README table)

# ---- What to pull out of the 168 TB virtual dataset -----------------------
FORECAST_DATE = "2026-05-13"   # init date to select (IFS cycle 50r1 reference date)
ACCUM_HOURS   = 24             # accumulation window: tp at this step = 0..N h total
MEMBER        = 0             # ensemble member index (0 = control, 1..50 perturbed)
TP_CANDIDATES = ["tp", "tprate"]   # var name is 'tp' in every era; probe to be safe


def open_published_store():
    """The minimal anonymous open, verbatim from the store's reference doc."""
    storage = icechunk.s3_storage(
        bucket=BUCKET, prefix=PREFIX,
        endpoint_url=ENDPOINT, region="us-east-1",
        anonymous=True,        # public read of the store metadata on source.coop
        from_env=False,        # ignore any stray AWS_* env vars
        force_path_style=True, # source.coop needs path-style addressing
    )
    # authorize anonymous byte-range reads of the virtual chunks on AWS
    auth = icechunk.containers_credentials(
        {CONTAINER: icechunk.s3_anonymous_credentials()})
    # Disable eager manifest preload -- source.coop returns sporadic HTTP 500s
    # under the default's parallel prefetch, which can fail the open. With
    # preload off, manifests load lazily on demand (slower open, but robust).
    cfg = icechunk.RepositoryConfig.default()
    cfg.manifest = icechunk.ManifestConfig(
        preload=icechunk.ManifestPreloadConfig(max_total_refs=0,
                                               max_arrays_to_scan=0))
    repo = icechunk.Repository.open(storage, config=cfg,
                                    authorize_virtual_chunk_access=auth)
    return repo.readonly_session("main")


def main() -> int:
    print(f"== opening s3://{BUCKET}/{PREFIX}")
    print(f"   anonymously via {ENDPOINT}, group {GROUP!r} ==")
    t0 = time.time()
    sess = open_published_store()
    ds = xr.open_zarr(sess.store, group=GROUP, consolidated=False, zarr_format=3)
    print(f"opened in {time.time()-t0:.1f}s")
    print(f"  dims: time={ds.sizes['time']}  number={ds.sizes['number']}  "
          f"step={ds.sizes['step']}  grid={ds.sizes['latitude']}x{ds.sizes['longitude']}")
    print(f"  virtual (unrealized) size: {ds.nbytes/1e12:.1f} TB "
          f"({ds.nbytes:,} bytes) -- none of it downloaded yet")

    # ---- Select: forecast date, member, accumulation window ---------------
    var = next((v for v in TP_CANDIDATES if v in ds), None)
    if var is None:
        raise SystemExit(f"none of {TP_CANDIDATES} present in group {GROUP!r}")

    want_date = np.datetime64(FORECAST_DATE)
    ti = int(np.argmin(np.abs(ds["time"].values - want_date)))
    init = np.datetime_as_string(ds["time"].values[ti], unit="D")
    si = int(np.argmin(np.abs(ds["step"].values - ACCUM_HOURS)))
    step = int(ds["step"].values[si])
    if init != FORECAST_DATE:
        print(f"  (note: {FORECAST_DATE} not in store; nearest init is {init})")
    print(f"\nSelecting {var!r}: init {init}  member {MEMBER}  "
          f"accumulation 0..{step} h")

    # ---- The one line that turns a virtual reference into real bytes ------
    # tp is stored in metres of water-equivalent; *1000 -> mm.
    t1 = time.time()
    tp_m = ds[var].isel(time=ti, number=MEMBER, step=si).values   # (ny, nx), metres
    dt = time.time() - t1
    tp_mm = tp_m.astype("float32") * 1000.0
    finite = float(np.isfinite(tp_mm).mean())
    print(f"  decoded a virtual chunk from {CONTAINER} in {dt:.1f}s")
    print(f"  shape {tp_mm.shape}  finite {finite:.3f}  "
          f"min {np.nanmin(tp_mm):.2f}  mean {np.nanmean(tp_mm):.2f}  "
          f"max {np.nanmax(tp_mm):.2f} mm")

    # ---- Plot -------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import BoundaryNorm
    except ImportError:
        raise SystemExit(
            "\n!! matplotlib not installed. Re-run with `uv run demo6_open_icechunk.py`.")

    lat = ds["latitude"].values
    lon = ds["longitude"].values
    out_png = Path(__file__).with_name("example.png")

    # precip-style discrete colormap in mm
    levels = [0, 1, 2, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300]
    cmap = plt.get_cmap("YlGnBu", len(levels) - 1)
    norm = BoundaryNorm(levels, cmap.N)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    im = ax.pcolormesh(lon, lat, tp_mm, cmap=cmap, norm=norm, shading="auto")
    cb = plt.colorbar(im, ax=ax, ticks=levels, shrink=0.85,
                      label=f"total precipitation, 0-{step} h (mm)")
    ax.set_xlabel("longitude (deg E)")
    ax.set_ylabel("latitude (deg N)")
    ax.set_title(f"ECMWF IFS ENS {GROUP} -- tp init {init}  member {MEMBER}  "
                 f"0-{step} h accumulation\n(one field out of a "
                 f"{ds.nbytes/1e12:.0f} TB virtual Icechunk store, opened anonymously)")
    plt.tight_layout()
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    print(f"\nSaved plot:   {out_png}")

    print("\nThe takeaway:")
    print(f"  One `xarray.open_zarr()` + one `.isel(...).values` gave you a")
    print(f"  decoded {var} field out of a {ds.nbytes/1e12:.0f} TB archive with")
    print(f"  no credentials and no data duplication. Demo 3 fans this same")
    print(f"  open out across members x steps x dates with Dask to compute")
    print(f"  ensemble exceedance probabilities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
