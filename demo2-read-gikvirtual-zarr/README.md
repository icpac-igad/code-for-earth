# Demo 2 — Read the GIK virtual Zarr

**Weekly rhythm:** Week 2 · Component 1 (standardise & open the archive)

A short, mentor-led demo. The full, self-contained tutorial and the production code live in the linked repositories — this folder only points you to them and frames the goal for the week.

## What the demo shows (quick, mentor side)

- Take the GIK Parquet references from Demo 1 and standardise them to **Zarr v3 / IceChunk** (via VirtualiZarr).
- Open the full archive with a **single `zarr.open()` / `xarray.open_dataset()`** call — metadata only, no data duplication.
- Inspect dimensions (member, step, time, lat/lon) and lazily slice a variable over East Africa.

## Self-contained tutorial & code

- Conversion pipeline (GIK → Zarr v3 / IceChunk) — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)

## Datasets

- Input references: [`E4DRR/gik-ecmwf-par`](https://huggingface.co/datasets/E4DRR/gik-ecmwf-par)
- Worked example store: [`ecmwf_ea_tp_icechunk`](https://source.coop/e4drr-project/forecasts/ecmwf_ea_tp_icechunk) — a single-month total-precipitation IceChunk store over East Africa

## Where this fits

The analysis-ready store opened here is the input that Demo 3 streams with Dask for exceedance analysis.
