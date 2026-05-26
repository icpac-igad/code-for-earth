# Demo 4 — CMORPH return-period thresholds

**Weekly rhythm:** Week 4 · Component 2 (extreme value thresholds)

A short, mentor-led demo. The full, self-contained tutorial and the production code live in the linked repositories — this folder only points you to them and frames the goal for the week.

## What the demo shows (quick, mentor side)

- Read the raw CMORPH 30-minute rainfall record (1998–2024) as a **VirtualiZarr** dataset.
- Compute annual maxima over the 7 accumulation windows and fit an **extreme value** distribution.
- Derive **return-period thresholds** (2, 5, 10, 20, 40, 100 yr) and write them as an IceChunk store.

## Self-contained tutorial & code

- Extreme value analysis method — [`ibf-thresholds-triggers` · `xarray-method/thresholds/CMORPH`](https://github.com/icpac-igad/ibf-thresholds-triggers/tree/xarray-method/thresholds/CMORPH)

## Datasets

- Raw record: [`cmorph-aws-s3-1998-2024.parquet`](https://huggingface.co/datasets/E4DRR/virtualizarr-stores/blob/main/cmorph-aws-s3-1998-2024.parquet) (`hf://datasets/E4DRR/virtualizarr-stores/cmorph-aws-s3-1998-2024.parquet`)
- Output store: [`cmorph_rp_icechunk`](https://source.coop/e4drr-project/observations/cmorph_rp_icechunk)

## Where this fits

Provides the return-period thresholds that Demo 3 compares the forecast ensemble against.
