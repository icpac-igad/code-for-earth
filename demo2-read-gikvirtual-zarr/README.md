# Demo 2 — Read the GIK virtual Zarr

**Weekly rhythm:** Week 2 · Component 1 (standardise & open the archive)

## The concepts

**HTTP Range requests** are the foundation of cloud-native data access. Every
object on S3 (and most HTTPS object stores) supports `Range: bytes=A-B` headers
— ask for any contiguous byte slice of any object, the server returns HTTP `206
Partial Content`. **Pay only for the bytes you ask for.** The GIK manifest from
Demo 1 (`url`, `byte_offset`, `byte_length`) is exactly what you need to issue
those requests against the cloud GRIB.

**GRIB2 decoding without `eccodes`.** GRIB2 is a complex binary format and the
classic decoder (`cfgrib`/`eccodes`) needs a system library that is painful to
install. [`gribberish`](https://pypi.org/project/gribberish/) is a Rust+Python
GRIB2 decoder that works on a raw byte buffer (no temp file, no system deps)
and is ~80× faster than `cfgrib`. It is what makes byte-range-stream-and-decode
fast enough to be practical in workers and notebooks.

**Streaming vs downloading.** The standard "download the GRIB, then open it"
workflow moves the whole 6+ GB file even if you only want one variable for one
member. With a GIK manifest + Range request you move ~700 KB instead — roughly
**10,000× less data**. The exact same pattern, parallelised, is what gives the
production pipeline its cost and speed.

**From one chunk to a virtual archive.** This demo fetches one GRIB message and
plots it. The conceptual leap to the production pipeline is just doing the same
thing for every (member, step, variable) lazily, behind a Zarr API — that is
what **VirtualiZarr** + **IceChunk** add on top of the GIK manifest, so the
user can `xarray.open_dataset(...)` the whole archive and slice it like any
local dataset.

## What the demo does

- Reads `../demo1-make-gik-virtual-zarr/example.parquet` (the manifest).
- Picks one row: 2 m air temperature for ensemble member 1 at step 0.
- Sends ONE HTTP `Range` request for that ~670 KB GRIB message out of the
  6.4 GB cloud GRIB.
- Decodes the returned bytes with `gribberish` into a `(721, 1440)` float
  array.
- Plots a global temperature map and saves `example.png`.

## Self-contained tutorial & code

- Conversion pipeline (GIK → Zarr v3 / IceChunk) — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)

## Datasets

- Input references: [`E4DRR/gik-ecmwf-par`](https://huggingface.co/datasets/E4DRR/gik-ecmwf-par)
- Worked example store: [`ecmwf_ea_tp_icechunk`](https://source.coop/e4drr-project/forecasts/ecmwf_ea_tp_icechunk) — a single-month total-precipitation IceChunk store over East Africa

## Where this fits

The analysis-ready store opened here is the input that Demo 3 streams with
Dask for exceedance analysis.

## Run locally (5 minutes, ~1 MB downloaded)

The script **`demo2_read_par.py`** is self-contained and uses
[PEP 723 inline metadata](https://peps.python.org/pep-0723/), so
[`uv`](https://docs.astral.sh/uv/) installs its dependencies (`pandas`,
`pyarrow`, `requests`, `gribberish`, `matplotlib`, `numpy`) in an ephemeral
environment automatically.

```bash
# 1. Make the manifest in Demo 1 (must run first):
cd demo1-make-gik-virtual-zarr
uv run demo1_make_par.py               # writes ./example.parquet

# 2. Use the manifest here:
cd ../demo2-read-gikvirtual-zarr
uv run demo2_read_par.py               # writes ./example.png
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
> [`gribberish`](https://pypi.org/project/gribberish/) — the same decoder
> ICPAC's production streamer uses to fan out across 12 vars × 51 members × 9
> steps in
> [`grib-index-kerchunk/ecmwf/stream_cgan_variables.py`](https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/stream_cgan_variables.py).
> Going from "one variable, one member, plotted" (this demo) to "lazy
> `zarr.open()` of the whole 51-member, 85-step archive via VirtualiZarr"
> is the next conceptual step — that's what the production conversion
> pipeline does.
