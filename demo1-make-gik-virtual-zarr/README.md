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
