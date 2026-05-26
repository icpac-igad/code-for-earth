# Demo 5 — Calendar-map web app

**Weekly rhythm:** Week 5 · Components 2 & 3 (visualisation & decision support)

A short, mentor-led demo. The full, self-contained tutorial and the production code live in the linked repositories — this folder only points you to them and frames the goal for the week.

## What the demo shows (quick, mentor side)

- Render a **GitHub-style calendar-map** summarising the daily flood risk signal across the ~1,000-day archive.
- Drill into a day via **MDX storymaps**: spatial exceedance maps, observed rainfall, and EM-DAT flood matches.
- Show the **admin-1 risk layer** (Component 3) — a Bayesian network in Julia via RxInfer.jl — feeding each daily cell, served through the CRMA web app.

## Self-contained tutorial & code

- CRMA web application — [`arco-ibf` · `cmra-web`](https://github.com/icpac-igad/arco-ibf/tree/cmra-web)
- Raster tiles (TiTiler + pgSTAC) — [`arco-ibf` · `titiler-pgstac`](https://github.com/icpac-igad/arco-ibf/tree/titiler-pgstac)
- Vector features (TiPg, OGC API – Features) — [`arco-ibf` · `tipg`](https://github.com/icpac-igad/arco-ibf/tree/tipg)
- Bayesian network risk — [`bn-ibf` · `jua-bnet/flood_ibf`](https://github.com/icpac-igad/bn-ibf/tree/jua-bnet/flood_ibf) ([`flood_bn_ibf_v1.jl`](https://github.com/icpac-igad/bn-ibf/blob/jua-bnet/flood_ibf/flood_bn_ibf_v1.jl), [`flood_data_prep.py`](https://github.com/icpac-igad/bn-ibf/blob/jua-bnet/flood_ibf/flood_data_prep.py))

## Datasets

- Exceedance dataset from Demo 3 · admin-1 boundaries (OCHA/GADM) · GPM IMERG observations · EM-DAT flood catalogue

## Where this fits

The endpoint of the pipeline: turns the exceedance and risk outputs into a quickly accessible decision-support view for the ~1,000-day archive.
