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

## Run locally (5 minutes, ~1 MB downloaded)

A small self-contained script in this folder, **`demo2_read_par.py`**,
consumes the GIK manifest produced by Demo 1 and uses it to stream ONE
variable for ONE ensemble member out of the 6.4 GB source GRIB via a single
HTTP `Range` request — then decodes and plots it.

```bash
# 1. Make the manifest in Demo 1 (must run first):
cd ../demo1-make-gik-virtual-zarr
pip install pandas pyarrow requests
python demo1_make_par.py                   # writes ./example.parquet

# 2. Use the manifest here:
cd ../demo2-read-gikvirtual-zarr
pip install pandas pyarrow requests gribberish matplotlib numpy
python demo2_read_par.py                   # writes ./example.png
```

Expected output (the streaming win in one line):

```
Picked:       param='2t'  number=1  levtype=sfc  step=0
  byte slice: offset=476,193,115  length=669,009 bytes  (0.67 MB, 0.010% of the full file)
GET           https://ecmwf-forecasts.s3.amazonaws.com/.../enfo-ef.grib2
  Range: bytes=476193115-476862123
  received 669,009 bytes  (HTTP 206 Partial Content)
Total bytes you transferred to do this (manifest + chunk): 810,908 (0.81 MB)
vs downloading the whole GRIB:                             6,396,517,751 (6.40 GB)
  -> ratio: 7888x less data transferred.
```

The script saves `example.png` — a global map of 2 m air temperature from
ECMWF ensemble member 1.

> The demo decodes one GRIB message at a time using
> [`gribberish`](https://pypi.org/project/gribberish/) (Rust+Python, no
> system `eccodes` needed) — the same decoder ICPAC's production streamer
> uses to fan out across 12 vars × 51 members × 9 steps in
> [`grib-index-kerchunk/ecmwf/stream_cgan_variables.py`](https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/stream_cgan_variables.py).
> Going from "one variable, one member, plotted" (this demo) to
> "lazy `zarr.open()` of the whole 51-member, 85-step archive via VirtualiZarr"
> is the next conceptual step — that's what the production conversion
> pipeline does.
