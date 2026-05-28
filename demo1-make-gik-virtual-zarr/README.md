# Demo 1 — Make a GIK virtual Zarr

**Weekly rhythm:** Week 1 · Component 1 (make the archive analysis-ready)

A short, mentor-led demo. The full, self-contained tutorial and the production code live in the linked repositories — this folder only points you to them and frames the goal for the week.

## What the demo shows (quick, mentor side)

- Pick one ECMWF IFS ensemble run from `s3://ecmwf-forecasts`.
- Build a **grib-index-kerchunk (GIK)** manifest: a lightweight reference file pointing to byte-ranges inside the original GRIB2 objects — no data copied.
- Wrap the manifest as a **virtual Zarr** so it can be opened with standard tools.
- Note the **IFS cycle 50r1 update (2026-05-12)** breaking change and which branch handles it.

## Self-contained tutorial & code

- Core ECMWF GIK pipeline — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)
- 50r1 breaking-change template — [`grib-index-kerchunk` · `ecmwf-50r1-template`](https://github.com/icpac-igad/grib-index-kerchunk/tree/ecmwf-50r1-template)

## Datasets

- Source GRIB2: `s3://ecmwf-forecasts`
- Example reference output: [`E4DRR/gik-ecmwf-par`](https://huggingface.co/datasets/E4DRR/gik-ecmwf-par)

## Where this fits

Produces the GIK Parquet references that Demo 2 standardises to Zarr v3 / IceChunk and reads.

## Run locally (5 minutes, ~2 MB downloaded)

A small self-contained script in this folder, **`demo1_make_par.py`**, builds
a GIK manifest for one ECMWF IFS ensemble file on `s3://ecmwf-forecasts` —
without downloading the multi-GB GRIB itself. It fetches only the JSON-lines
`.index` companion file (~2 MB of text) and parses it into a Parquet manifest
(~140 KB) of `(param, number, levtype, level, step, byte_offset, byte_length, url)`.

```bash
cd demo1-make-gik-virtual-zarr
pip install pandas pyarrow requests        # the three deps
python demo1_make_par.py                   # writes ./example.parquet
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

> The demo is intentionally a hand-parsed `.index` reader in ~80 lines so you
> can read it end-to-end. The production version uses
> `kerchunk._grib_idx.parse_grib_idx` and scales the same idea to 51 members
> × 85 forecast hours via Lithops/Cloud Run — see
> [`grib-index-kerchunk/ecmwf/run_lithops_ecmwf.py`](https://github.com/icpac-igad/grib-index-kerchunk/blob/main/ecmwf/run_lithops_ecmwf.py).

**Note on dates:** ECMWF Open Data on AWS retains the most recent ~30 days
of real-time forecasts. If `DATE` in the script has aged out, bump it to a
recent forecast date (any YYYYMMDD within the last month).
