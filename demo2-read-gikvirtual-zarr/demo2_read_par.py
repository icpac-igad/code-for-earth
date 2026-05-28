#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "pyarrow",
#   "requests",
#   "gribberish",
#   "matplotlib",
#   "numpy",
# ]
# ///
"""
demo2 — use the GIK manifest from demo1: byte-range-fetch ONE variable
        for ONE ensemble member, decode it, plot it.

This is where the streaming win becomes visible:
    - Read the local Parquet from demo1 (~140 KB on disk).
    - Pick 2m air temperature for ensemble member 1.
    - Send ONE HTTP request with `Range: bytes=offset-end` for just
      that GRIB message (~650 KB) out of the full 6.4 GB GRIB.
    - Decode it with gribberish (pure Python+Rust, no eccodes/cfgrib).
    - Plot it with matplotlib and save example.png.

Run:
    uv run demo2_read_par.py            # uv handles the deps automatically

Production version (used by ICPAC's cGAN streamer + plot pipeline):
    https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/stream_cgan_variables.py
    -- same byte-range + gribberish pattern, parallelised over 12 vars × 51
    members × 9 steps with a ThreadPoolExecutor.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# Where demo1 wrote its manifest:
PAR = Path(__file__).resolve().parent.parent / "demo1-make-gik-virtual-zarr" / "example.parquet"

# ECMWF 0.25° global grid: 721 lats × 1440 lons, lat 90 -> -90, lon 0 -> 359.75
GRID = (721, 1440)

# What to pick out of the manifest:
PICK_PARAM   = "2t"   # 2-metre air temperature (instantaneous, has data at step=0)
PICK_NUMBER  = 1      # ensemble member 1 (1..50; -1 would be control if present)


def main() -> int:
    if not PAR.exists():
        raise SystemExit(
            f"\n!! Manifest not found: {PAR}\n"
            f"   Run demo1 first:\n"
            f"     cd ../demo1-make-gik-virtual-zarr && uv run demo1_make_par.py")

    df = pd.read_parquet(PAR)
    sel = df[(df["param"] == PICK_PARAM) & (df["number"] == PICK_NUMBER)]
    if sel.empty:
        raise SystemExit(
            f"\n!! No row for param={PICK_PARAM!r} number={PICK_NUMBER} in {PAR.name}.\n"
            f"   Available params: {sorted(df['param'].unique())[:10]}...")
    row = sel.iloc[0]
    grib_url = row["url"]
    offset, length = int(row["offset"]), int(row["length"])

    # Compute the full GRIB size from the manifest itself (no extra HTTP call):
    full_size = int(df["offset"].max() + df.loc[df["offset"].idxmax(), "length"])
    pct = length / full_size * 100

    print(f"Manifest:     {PAR}  ({PAR.stat().st_size:,} bytes)")
    print(f"Source GRIB:  {grib_url}")
    print(f"  full size:  {full_size:,} bytes  ({full_size/1e9:.2f} GB)")
    print(f"Picked:       param={PICK_PARAM!r}  number={PICK_NUMBER}  "
          f"levtype={row['levtype']}  step={row['step']}")
    print(f"  byte slice: offset={offset:,}  length={length:,} bytes  "
          f"({length/1e6:.2f} MB, {pct:.3f}% of the full file)")

    # ---- The byte-range request -------------------------------------------
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    print(f"\nGET           {grib_url}")
    print(f"  Range: {headers['Range']}")
    r = requests.get(grib_url, headers=headers, timeout=120)
    if r.status_code != 206:
        raise SystemExit(f"expected HTTP 206 Partial Content; got {r.status_code}")
    grib_bytes = r.content
    print(f"  received {len(grib_bytes):,} bytes  (HTTP {r.status_code} Partial Content)")

    transferred = PAR.stat().st_size + len(grib_bytes)
    print(f"\nTotal bytes you transferred to do this (manifest + chunk): "
          f"{transferred:,} ({transferred/1e6:.2f} MB)")
    print(f"vs downloading the whole GRIB:                             "
          f"{full_size:,} ({full_size/1e9:.2f} GB)")
    print(f"  -> ratio: {full_size/transferred:.0f}x less data transferred.")

    # ---- Decode -----------------------------------------------------------
    try:
        import gribberish
    except ImportError:
        raise SystemExit(
            "\n!! gribberish not installed.\n"
            "   Easiest fix: re-run with `uv run demo2_read_par.py` (uv reads\n"
            "   the inline PEP 723 metadata at the top of this script and\n"
            "   installs the deps in an ephemeral env).")
    flat = gribberish.parse_grib_array(grib_bytes, 0)
    grid = np.asarray(flat).reshape(GRID).astype(np.float32)
    print(f"\nDecoded:      shape={grid.shape}  dtype={grid.dtype}  "
          f"min={grid.min():.2f}K  max={grid.max():.2f}K")

    # ---- Plot -------------------------------------------------------------
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise SystemExit(
            "\n!! matplotlib not installed. Easiest fix: re-run with"
            " `uv run demo2_read_par.py`.")

    data_c = grid - 273.15   # K -> degC for 2m temperature
    out_png = Path(__file__).with_name("example.png")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    im = ax.imshow(
        data_c,
        extent=[0, 360, -90, 90],       # lon range, lat range
        origin="upper",                  # row 0 is lat=+90
        cmap="RdYlBu_r",
        aspect="auto",
    )
    plt.colorbar(im, ax=ax, label="2 m air temperature (°C)", shrink=0.85)
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.set_title(f"ECMWF IFS ENS — {PICK_PARAM} member {PICK_NUMBER} "
                 f"step={row['step']}h  ({len(grib_bytes)/1e6:.2f} MB "
                 f"of a {full_size/1e9:.2f} GB GRIB)")
    plt.tight_layout()
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    print(f"\nSaved plot:   {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
