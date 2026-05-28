#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "pyarrow",
#   "requests",
# ]
# ///
"""
demo1 — make a GIK manifest for ONE ECMWF IFS ensemble file.

This is the grib-index-kerchunk method in ~80 lines.

Idea:
    ECMWF publishes a tiny JSON-lines `.index` file next to every GRIB2
    object on `s3://ecmwf-forecasts`. Each line is a JSON record describing
    one GRIB message:

        {"_offset": 0, "_length": 1186380, "param": "10u", "number": 1,
         "levtype": "sfc", "step": "0", ...}

    We parse it into a Parquet manifest of (param, number, levtype, level,
    step, byte_offset, byte_length, url). demo2 then reads ONE row's bytes
    out of the multi-GB GRIB via an HTTP Range request — no full download,
    no eccodes/cfgrib needed for this step.

Run:
    uv run demo1_make_par.py            # uv reads the inline metadata above
                                        # and installs deps in an ephemeral env

    NOT  `uv run python demo1_make_par.py`  — putting `python` between
    `uv run` and the script name bypasses the inline metadata and uses
    whatever `python` is on PATH, which may be missing pyarrow / requests.

Output:
    ./example.parquet
    (consumed by ../demo2-read-gikvirtual-zarr/demo2_read_par.py)

Production version of this pattern (used by ICPAC's pipeline):
    https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/run_lithops_ecmwf.py
    -- same JSON-lines parse, scaled across 51 members × 85 forecast hours
    via Lithops/Cloud Run.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    import pandas as pd
    import pyarrow  # noqa: F401  -- explicit so a missing parquet engine fails here
    import requests
except ImportError as e:
    sys.exit(
        f"\n!! {e.name} not importable.\n"
        f"   Run this script with `uv run demo1_make_par.py` (no `python` in\n"
        f"   between) so uv reads the PEP 723 metadata at the top and installs\n"
        f"   pandas + pyarrow + requests in an ephemeral env automatically.\n"
        f"   If you cannot use uv, install manually:\n"
        f"       pip install pandas pyarrow requests")

# ---- A tiny, reproducible worked example ----------------------------------
# ECMWF Open Data on AWS retains the most recent ~30 days of real-time
# forecasts. If the date below has aged out, bump DATE to a recent forecast.
# 2026-05-13 00z is the IFS cycle 50r1 reference date (see the
# `ecmwf-50r1-template` branch of grib-index-kerchunk).
DATE  = "20260513"   # YYYYMMDD
RUN   = "00"         # 00 / 06 / 12 / 18
FHOUR = "0"          # forecast hour — not zero-padded in ECMWF URLs

BASE      = "https://ecmwf-forecasts.s3.amazonaws.com"
PREFIX    = f"{DATE}/{RUN}z/ifs/0p25/enfo/{DATE}{RUN}0000-{FHOUR}h-enfo-ef"
GRIB_URL  = f"{BASE}/{PREFIX}.grib2"
INDEX_URL = f"{BASE}/{PREFIX}.index"
OUT       = Path(__file__).with_name("example.parquet")


def parse_index(index_text: str, grib_url: str) -> pd.DataFrame:
    """Parse an ECMWF .index file (JSON-lines) into a manifest DataFrame.

    Keys we care about in each line:
        _offset, _length     -- byte position of this message in the GRIB
        param                -- short variable name ('tp', '10u', 't', ...)
        number               -- ensemble member 1..50 (absent in pre-50r1
                                control 'cf' rows; absent in oper/fc rows)
        levtype, levelist    -- 'sfc'/'sol'/'pl' and level value
        step                 -- forecast hour as a string
    """
    rows = []
    for line in index_text.strip().splitlines():
        rec = json.loads(line)
        rows.append({
            "param":    rec.get("param"),
            "number":   int(rec["number"]) if "number" in rec else -1,
            "levtype":  rec.get("levtype"),
            "levelist": str(rec.get("levelist") or ""),
            "step":     str(rec.get("step") or ""),
            "offset":   int(rec["_offset"]),
            "length":   int(rec["_length"]),
            "url":      grib_url,
        })
    return pd.DataFrame(rows)


def main() -> int:
    print(f"Fetching .index  {INDEX_URL}")
    r = requests.get(INDEX_URL, timeout=30)
    if r.status_code == 404:
        raise SystemExit(
            "\n!! 404 from ECMWF Open Data.\n"
            "   Real-time forecasts are kept for ~30 days, so this DATE may have\n"
            "   aged out. Edit demo1_make_par.py and set DATE to a recent forecast\n"
            "   (any YYYYMMDD within the last 30 days).")
    r.raise_for_status()
    index_text = r.text
    n_msgs = len(index_text.strip().splitlines())
    print(f"  .index is {len(index_text):,} bytes  ({n_msgs} GRIB messages)")

    print(f"\nHEAD             {GRIB_URL}")
    grib_size = int(requests.head(GRIB_URL, timeout=30).headers["Content-Length"])
    print(f"  full GRIB is {grib_size:,} bytes ({grib_size/1e9:.2f} GB)"
          " — we will NOT download it")

    df = parse_index(index_text, GRIB_URL)
    df.to_parquet(OUT, engine="pyarrow")
    print(f"\nWrote {OUT.name}  ({OUT.stat().st_size:,} bytes)")
    print(f"  manifest rows: {len(df)}")
    print(f"  unique params: {df['param'].nunique()}  "
          f"members: {df[df['number']>0]['number'].nunique()} "
          f"(plus {(df['number']==-1).any() and 'a control row' or 'no control row'})")

    print("\nA few example rows from the manifest:")
    print(f"  {'param':<6} {'#mem':>4} {'levtype':<7} {'lev':<6} {'step':<5}"
          f" {'offset':>13} {'length':>9}")
    for _, x in df.head(8).iterrows():
        print(f"  {str(x['param']):<6} {int(x['number']):>4} "
              f"{str(x['levtype']):<7} {str(x['levelist']):<6} "
              f"{str(x['step']):<5} {int(x['offset']):>13,} {int(x['length']):>9,}")

    print("\nThe takeaway:")
    print(f"  We've described a {grib_size/1e9:.2f} GB cloud object with a "
          f"{OUT.stat().st_size/1e3:.1f} KB local manifest.")
    print(f"  demo2 will use this manifest to byte-range-fetch ONE variable")
    print(f"  for ONE member (~1-2 MB) out of the full file. Run:")
    print(f"     cd ../demo2-read-gikvirtual-zarr && uv run demo2_read_par.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
