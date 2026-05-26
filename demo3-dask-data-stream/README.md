# Demo 3 — Dask data streaming

**Weekly rhythm:** Week 3 · Component 2 (retrospective ensemble exceedance analysis)

A short, mentor-led demo. The full, self-contained tutorial and the production code live in the linked repositories — this folder only points you to them and frames the goal for the week.

## What the demo shows (quick, mentor side)

- Stream the analysis-ready archive (Demo 2) with **Dask** in data-streaming mode — no full download.
- For East Africa grid cells, compute rainfall **accumulations** over 7 windows (3 h, 6 h, 12 h, 24 h, 48 h, 72 h, 7 d) across the 51-member ensemble.
- Derive **empirical exceedance probabilities** — the fraction of members exceeding a threshold — lazily and at scale.

## Self-contained tutorial & code

- GIK / virtual-store access patterns and streaming — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)
- Exceedance pipeline building blocks: `xarray`, `numpy`, `scipy.stats`, `dask`

## Datasets

- Forecast input: the Zarr v3 / IceChunk store from Demo 2 (e.g. [`ecmwf_ea_tp_icechunk`](https://source.coop/e4drr-project/forecasts/ecmwf_ea_tp_icechunk))
- Thresholds: the return-period store from Demo 4 ([`cmorph_rp_icechunk`](https://source.coop/e4drr-project/observations/cmorph_rp_icechunk))

## Where this fits

Combines the forecast stream with Demo 4's thresholds to produce the exceedance dataset visualised in Demo 5.
