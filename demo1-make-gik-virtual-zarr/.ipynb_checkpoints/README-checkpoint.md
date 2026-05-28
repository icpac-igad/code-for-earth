# Demo 1 — Make a GIK virtual Zarr

**Weekly rhythm:** Week 1 · Component 1 (make the archive analysis-ready)

## The concepts

**GRIB2** is the standard format for weather forecast data — compact, efficient,
and widely supported, but **not cloud-native**: you cannot `xarray.open()` a
remote GRIB2 file, because it has no built-in chunk/byte index that a remote
reader can use.

**Every GRIB2 file on `s3://ecmwf-forecasts` ships with a tiny companion `.index`
file.** Each line is a one-line JSON record describing one GRIB message — its
variable, ensemble member, forecast step, and crucially its **byte offset and
length** inside the GRIB. Index files are KBs; the GRIBs are GBs.

**Grib-Index-Kerchunk (GIK)** turns that `.index` into a portable **manifest**
(one row per GRIB message: `param`, `number`, `levtype`, `level`, `step`,
`byte_offset`, `byte_length`, `url`) saved as a Parquet file. The manifest is a
**lightweight reference** — it points into the cloud GRIB, no data is copied.
Demo 2 then uses the manifest to do HTTP byte-range reads of just the messages
it needs.

The same manifest can be wrapped as a **virtual Zarr** so it can be opened with
standard tools (`zarr.open()`, `xarray.open_dataset()`) — that is what Demo 2
covers.

> The IFS cycle 50r1 update (live 2026-05-12) is a breaking change to the
> ensemble layout — see the
> [`ecmwf-50r1-template`](https://github.com/icpac-igad/grib-index-kerchunk/tree/ecmwf-50r1-template)
> branch for the template rebuild.

## What the demo does

- Picks one ECMWF IFS ensemble run from `s3://ecmwf-forecasts`.
- Fetches only its JSON-lines `.index` companion (~2 MB of text).
- Parses each line into a row of a Parquet **manifest** of byte ranges.
- Writes `example.parquet` (~140 KB) that describes the full 6+ GB GRIB
  without copying any of its data.

## Self-contained tutorial & code

- Core ECMWF GIK pipeline — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)
- 50r1 breaking-change template — [`grib-index-kerchunk` · `ecmwf-50r1-template`](https://github.com/icpac-igad/grib-index-kerchunk/tree/ecmwf-50r1-template)

## Datasets

- Source GRIB2: `s3://ecmwf-forecasts`
- Example reference output: [`E4DRR/gik-ecmwf-par`](https://huggingface.co/datasets/E4DRR/gik-ecmwf-par)

## Where this fits

Produces the GIK Parquet references that Demo 2 standardises to Zarr v3 /
IceChunk and reads.

## Run locally (5 minutes, ~2 MB downloaded)

The script **`demo1_make_par.py`** is self-contained and uses
[PEP 723 inline metadata](https://peps.python.org/pep-0723/), so
[`uv`](https://docs.astral.sh/uv/) installs its three dependencies
(`pandas`, `pyarrow`, `requests`) in an ephemeral environment automatically —
no manual `pip install`, no virtualenv to manage.

```bash
cd demo1-make-gik-virtual-zarr
uv run demo1_make_par.py               # writes ./example.parquet
```

Expected output (the streaming-vs-download magic in numbers):

```
.index is 1,993,447 bytes  (8500 GRIB messages)
full GRIB is 6,396,517,751 bytes (6.40 GB) — we will NOT download it
Wrote example.parquet  (141,899 bytes)
We've described a 6.40 GB cloud object with a 141.9 KB local manifest.
```

Then run Demo 2 (in `../demo2-read-gikvirtual-zarr/`) to byte-range-fetch
one variable for one ensemble member out of that 6.4 GB file.

> The script is intentionally a hand-parsed `.index` reader in ~80 lines so
> you can read it end-to-end and see exactly what a GIK manifest is. The
> production version uses `kerchunk._grib_idx.parse_grib_idx` and scales the
> same idea to 51 members × 85 forecast hours via Lithops/Cloud Run — see
> [`grib-index-kerchunk/ecmwf/run_lithops_ecmwf.py`](https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/run_lithops_ecmwf.py).

**Note on dates:** ECMWF Open Data on AWS retains the most recent ~30 days
of real-time forecasts. If `DATE` in the script has aged out, bump it to a
recent forecast date (any YYYYMMDD within the last month).
