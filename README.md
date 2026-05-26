# code-for-earth

Coordination hub for **ECMWF Code for Earth 2026 — Challenge 41: Missed Opportunities in Flood Disaster Risk Management** 

This repository coordinates the **two teams** working on the challenge: it holds shared documentation, links to component repositories and datasets.

## The challenge in brief

ECMWF's open IFS ensemble archive on AWS S3 (`s3://ecmwf-forecasts`) is the largest freely available NWP dataset — over 1 PB of GRIB2, 51 ensemble members, 85 steps (0–360 h), accumulated since May 2023. Three barriers stop it being used for flood risk management in East Africa:

1. **GRIB2 is not cloud-native** — raw GRIB2 objects can't be opened directly by `xarray`/`zarr-python`.
2. **No systematic flood-relevant forecast evaluation** — forecast performance during past flood events is poorly understood.
3. **No link from forecast probability to decision support** — no lightweight, reproducible way to turn ensemble signals into admin-1 risk assessments or to explore the ~1,000-day archive without running the full pipeline.

**Goal:** evaluate Grib-Index-Kerchunk(GIK) and benchmark methods for making the archive analysis-ready, then use the result for retrospective flood risk assessment across East Africa — computing rainfall-based exceedance probabilities from ~1,000 days of forecasts and visualising the results cost-effectively.

## The three components

| # | Component | Deliverable |
|---|-----------|-------------|
| 1 | **Make GRIB2 analysis-ready.** Benchmark Dynamical.org (full Zarr, duplicates data) vs. [grib-index-kerchunk](https://github.com/icpac-igad/grib-index-kerchunk) (lightweight manifests, no duplication) on cost/speed/scale. Standardise GIK manifests to **Zarr v3 / IceChunk** (via VirtualiZarr) for one-call `zarr.open()` access. | Public virtual Zarr stores (metadata only), a reproducible conversion pipeline, and a benchmarking report. |
| 2 | **Retrospective ensemble exceedance analysis + visualisation.** Per grid cell × ~1,000 days, compute empirical exceedance probabilities from the 51-member ensemble across 7 accumulation windows (3 h–7 d) vs. return-period thresholds (2–100 yr) from CMORPH. Visualise via a GitHub-style calendar-map with per-day MDX storymaps (NASA VEDA-UI / TiTiler). | A Zarr v3 exceedance dataset (date × grid × window × return period), the pipeline (xarray, numpy, scipy, dask), and the calendar-map. |
| 3 | **(Optional) Admin-1 risk assessment.** Combine Component 2 probabilities with GPM IMERG observations to produce daily admin-1 flood risk per day. A **Bayesian network** prototype exists at ICPAC ([bn-ibf `jua-bnet/flood_ibf`](https://github.com/icpac-igad/bn-ibf/tree/jua-bnet/flood_ibf)) — inference runs in Julia via **RxInfer.jl** ([`flood_bn_ibf_v1.jl`](https://github.com/icpac-igad/bn-ibf/blob/jua-bnet/flood_ibf/flood_bn_ibf_v1.jl)) with input prepared in Python ([`flood_data_prep.py`](https://github.com/icpac-igad/bn-ibf/blob/jua-bnet/flood_ibf/flood_data_prep.py)) — linked to the **CRMA** web application; alternatives include threshold-based alerts or weighted scoring. Each daily risk output feeds the corresponding cell of the calendar-map. | Daily admin-1 risk script + risk layer integrated into the Component 2 calendar-map and storymaps. |

## Weekly demos

To set a weekly coordination rhythm, each folder below holds a short **mentor-led demo** for that week. The demos are deliberately quick pointers — the **self-contained tutorials and production code** live in the component repositories listed under [Key codebases](#key-codebases). Each demo's output feeds the next.

| Week | Demo | Focus | Component |
|------|------|-------|-----------|
| 1 | [`demo1-make-gik-virtual-zarr`](demo1-make-gik-virtual-zarr/) | Build a GIK manifest from raw GRIB2 and wrap it as a virtual Zarr | 1 |
| 2 | [`demo2-read-gikvirtual-zarr`](demo2-read-gikvirtual-zarr/) | Standardise to Zarr v3 / IceChunk and open with one `zarr.open()` | 1 |
| 3 | [`demo3-dask-data-stream`](demo3-dask-data-stream/) | Stream the archive with Dask; compute ensemble exceedance probabilities | 2 |
| 4 | [`demo4-cmorph-return-period`](demo4-cmorph-return-period/) | Extreme value analysis: return-period thresholds from raw CMORPH | 2 |
| 5 | [`demo5-calendar-web-app`](demo5-calendar-web-app/) | Calendar-map web app, storymaps, and admin-1 BN risk layer | 2 & 3 |

## Key datasets

- **ECMWF IFS ensemble** — `s3://ecmwf-forecasts` (primary forecast data)
- **Existing IFS Zarr** — [dynamical.org](https://dynamical.org/catalog/models/ecmwf-ifs-ens/)
- **GIK Parquet references** — [E4DRR/gik-ecmwf-par](https://huggingface.co/datasets/E4DRR/gik-ecmwf-par) (input for Zarr v3 / IceChunk conversion)
- **ECMWF total precipitation example store** — [`ecmwf_ea_tp_icechunk`](https://source.coop/e4drr-project/forecasts/ecmwf_ea_tp_icechunk) on Source Cooperative: a single-month IceChunk store of total precipitation over East Africa, as a worked example of the analysis-ready target format.
- **CMORPH 30-min rainfall** — [E4DRR/virtualizarr-stores](https://huggingface.co/datasets/E4DRR/virtualizarr-stores) (return-period thresholds). The raw record used for the extreme value analysis is the VirtualiZarr dataset [`cmorph-aws-s3-1998-2024.parquet`](https://huggingface.co/datasets/E4DRR/virtualizarr-stores/blob/main/cmorph-aws-s3-1998-2024.parquet) (`hf://datasets/E4DRR/virtualizarr-stores/cmorph-aws-s3-1998-2024.parquet`, 1998–2024).
- **CMORPH return-period (extreme value) store** — [`cmorph_rp_icechunk`](https://source.coop/e4drr-project/observations/cmorph_rp_icechunk) on Source Cooperative: the IceChunk store of return-period thresholds derived from the CMORPH record via extreme value analysis (the 2–100 yr thresholds used in Component 2).
- **GPM IMERG** — observational evidence for the forecast dates
- **EM-DAT flood catalogue** — validation against recorded floods
- **Admin-1 boundaries (East Africa)** — OCHA/GADM spatial aggregation units

## Key codebases

The working code for the challenge lives across two ICPAC repositories. Each branch below addresses a specific part of the pipeline:

### [grib-index-kerchunk](https://github.com/icpac-igad/grib-index-kerchunk) — making the archive analysis-ready (Component 1)

- **[`ecmwf-50r1-template`](https://github.com/icpac-igad/grib-index-kerchunk/tree/ecmwf-50r1-template)** — handles the ECMWF **IFS cycle 50r1 update (effective 2026-05-12)**, which introduced a **breaking change for the Parquet reference creator**. This branch carries the updated template/parsing needed to keep generating GIK manifests against the new GRIB2 layout.
- **[`main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)** — the main working method for ECMWF: the core GIK pipeline that builds the kerchunk/Parquet byte-range references over the IFS ensemble archive (the input to Zarr v3 / IceChunk standardisation).

### [arco-ibf](https://github.com/icpac-igad/arco-ibf) — decision support and visualisation (Components 2 & 3)

- **[`cmra-web`](https://github.com/icpac-igad/arco-ibf/tree/cmra-web)** — the CMRA web application: the front-end/decision-support layer that surfaces the retrospective analysis and risk products to users.
- **[`titiler-pgstac`](https://github.com/icpac-igad/arco-ibf/tree/titiler-pgstac)** — dynamic raster tiling via **TiTiler** backed by **pgSTAC**, serving the exceedance/spatial map layers for the storymaps and calendar-map.
- **[`tipg`](https://github.com/icpac-igad/arco-ibf/tree/tipg)** — vector feature serving via **TiPg** (OGC API – Features) for the admin-1 boundaries and risk layers consumed by the visualisation front-end.

### [ibf-thresholds-triggers](https://github.com/icpac-igad/ibf-thresholds-triggers) — return-period thresholds (Component 2 inputs)

- **[`xarray-method/thresholds/CMORPH`](https://github.com/icpac-igad/ibf-thresholds-triggers/tree/xarray-method/thresholds/CMORPH)** — the extreme value analysis method: computes return-period thresholds (2–100 yr) from the raw CMORPH rainfall record (`cmorph-aws-s3-1998-2024.parquet`), producing the [`cmorph_rp_icechunk`](https://source.coop/e4drr-project/observations/cmorph_rp_icechunk) store.

## Links

- Challenge issue: [ECMWFCode4Earth/Challenges_2026 #16](https://github.com/ECMWFCode4Earth/Challenges_2026/issues/16)
- ECMWF Code for Earth: https://codeforearth.ecmwf.int/
