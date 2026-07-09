# Demo 6 — Open the published ECMWF IFS Icechunk virtual dataset

**Weekly rhythm:** Week 6 · Component 1 (the analysis-ready archive, published)

## The concepts

**This is where Component 1 lands.** Demo 1 built a GIK manifest from one
GRIB's `.index`; Demo 2 byte-range-read one message out of one GRIB. Demo 6
opens the **whole archive** — 51 forecast dates × 51 members × 85 steps — as a
single Zarr dataset with **one `xarray.open_zarr()`** and **zero credentials**.

**A virtual Icechunk store holds no data.** The store published on
[**source.coop**](https://source.coop/e4drr-project/forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd)
is pure metadata: a repo pointer, snapshots, and manifests. Every chunk is a
**virtual reference** — a `(url, byte_offset, byte_length)` pointer — into the
public `s3://ecmwf-forecasts/` GRIB archive on AWS (the same GRIBs Demo 1/2 read
by hand). Nothing is copied. `xarray` reports the store as **~169 TB**, but that
is the *unrealized* size; you only ever move the few hundred KB of the field you
actually slice.

**Two anonymous reads, no credentials.** A reader needs only:
- **anonymous** GET/LIST on source.coop (the store metadata), and
- **anonymous** GET on `ecmwf-forecasts` (the GRIB bytes the chunks point at).

When you slice a variable, icechunk resolves the reference, issues an anonymous
byte-range GET against `ecmwf-forecasts`, and decodes the returned bytes through
the **`gribberish` Zarr v3 codec** — the same decoder from Demo 2, now wired in
behind the Zarr API so you never touch bytes yourself.

**Total precipitation is the flood-relevant field.** This demo reads `tp` (total
precipitation) for one forecast init date, one member, one accumulation window.
`tp` is **accumulated from step 0**, so `tp` at step=24 *is* the 0–24 h total
(stored in metres; ×1000 → mm). Step 0 is all-zero by definition. That per-day,
per-member rainfall total is exactly what Demo 3 fans out across the ensemble to
compute exceedance probabilities.

## The store is multi-era (three groups, not one)

The store keeps each IFS **schema era** in its own group, because grid, level
count, and variable set differ across ECMWF model-cycle upgrades. Arrays live
under `{era}/00z`, never at the root.

| | value |
|---|---|
| Endpoint | `https://data.source.coop` |
| Bucket | `e4drr-project` |
| Prefix | `forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd` |
| Groups | `0p4/00z`, `49r1/00z`, `50r1/00z` ← **one per schema era** |
| Virtual chunk source | `s3://ecmwf-forecasts/` (anonymous) |
| Chunk codec | `gribberish` (Zarr v3) |

| Group | Grid | pl levels | Data vars | Window (00z) |
|---|---|---|---|---|
| `0p4/00z`  | 451 × 900  | 9  | 19 | 2023-01-18 .. 2024-02-28 |
| `49r1/00z` | 721 × 1440 | 13 | 59 | 2024-02-29 .. 2026-05-12 |
| `50r1/00z` | 721 × 1440 | 14 | 54 | 2026-05-12 .. present |

All three share `number=51` (control + 50 perturbed) and `step=85`. This demo
opens the current **`50r1/00z`** stream.

## What the demo does

- Opens the published store **anonymously** over the source.coop S3 endpoint.
- Opens the `50r1/00z` group as an xarray dataset (~169 TB, virtual).
- Selects `tp` for one **forecast init date** (`2026-05-13`), member 0, at the
  24 h step — i.e. the 0–24 h precipitation total.
- Resolves that one virtual chunk (anonymous byte-range read of
  `ecmwf-forecasts` + `gribberish` decode) into a `(721, 1440)` array.
- Converts metres → mm and plots a global precipitation map, saving
  `example.png`.

## Self-contained tutorial & code

- Conversion pipeline (GIK → Zarr v3 / IceChunk) — [`grib-index-kerchunk` · `main/ecmwf`](https://github.com/icpac-igad/grib-index-kerchunk/tree/main/ecmwf)
- 50r1 breaking-change template — [`grib-index-kerchunk` · `ecmwf-50r1-template`](https://github.com/icpac-igad/grib-index-kerchunk/tree/ecmwf-50r1-template)

## Datasets

- Published store: [`ecmwf_ifs_ens_aws_s3_icechunk_vd`](https://source.coop/e4drr-project/forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd) on Source Cooperative
- Virtual chunk source: `s3://ecmwf-forecasts` (public AWS, anonymous)
- Worked single-month example: [`ecmwf_ea_tp_icechunk`](https://source.coop/e4drr-project/forecasts/ecmwf_ea_tp_icechunk)

## Where this fits

Demos 1–2 showed *how* the manifests are built and read one message at a time.
This demo opens the **published product** those manifests become. The `tp` field
read here is the input Demo 3 streams with Dask to compute ensemble exceedance
probabilities for Component 2.

## Run locally (~2 minutes, a few hundred KB downloaded)

The script **`demo6_open_icechunk.py`** is self-contained and uses
[PEP 723 inline metadata](https://peps.python.org/pep-0723/), so
[`uv`](https://docs.astral.sh/uv/) installs its dependencies (`icechunk`,
`zarr`, `xarray`, `numpy`, `gribberish`, `s3fs`, `matplotlib`) in an ephemeral
environment automatically — no manual `pip install`, no virtualenv to manage.

### Step 0 — install `uv` (one-time)

`uv` is a single self-contained binary; installing it needs no Python and no
admin rights. Pick one:

```bash
# macOS / Linux (official installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# or, if you already have Python tooling
pipx install uv        # or:  pip install uv
```

Open a new terminal (so `uv` is on `PATH`) and check it:

```bash
uv --version           # e.g. uv 0.10.0
```

`uv` will download and manage its own Python if you don't have a suitable one —
you do **not** need to install Python separately.

### Step 1 — run the demo

```bash
cd demo6-gik-ecmwf-ifs-icechunk-virtualdataset
uv run demo6_open_icechunk.py          # writes ./example.png
```

The **first** run installs the dependencies into an ephemeral, cached
environment (takes a bit longer); later runs reuse the cache and start fast.

> ⚠ Use `uv run demo6_open_icechunk.py`, **not**
> `uv run python demo6_open_icechunk.py`. The `python` in the middle makes uv
> hand the script to whatever `python` is on `PATH` (which may be a Coiled /
> conda env missing `icechunk` or `gribberish`) and the PEP 723 metadata at the
> top of the script is silently ignored. Same applies to every demo here.

> Run it **without** any `AWS_*` env vars set. `from_env=False` ignores them
> anyway, but the whole point is that **no credentials** are needed — not for
> the source.coop metadata, not for the ecmwf-forecasts GRIB bytes.

Expected output (a global field out of a 169 TB store, opened anonymously):

```
== opening s3://e4drr-project/forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd
   anonymously via https://data.source.coop, group '50r1/00z' ==
opened in 25.0s
  dims: time=51  number=51  step=85  grid=721x1440
  virtual (unrealized) size: 168.9 TB (168,940,917,752,650 bytes) -- none of it downloaded yet

Selecting 'tp': init 2026-05-13  member 0  accumulation 0..24 h
  decoded a virtual chunk from s3://ecmwf-forecasts/ in 6.3s
  shape (721, 1440)  finite 1.000  min 0.00  mean 2.50  max 326.64 mm

Saved plot:   .../example.png
```

The script saves `example.png` — a global map of the 0–24 h total precipitation
from ECMWF ensemble member 0, initialised 2026-05-13.

### Reading a different field

Edit the constants at the top of `demo6_open_icechunk.py`:

- `GROUP` — pick the schema era (`0p4/00z`, `49r1/00z`, `50r1/00z`).
- `FORECAST_DATE` — any init date inside that era's window (nearest is used).
- `ACCUM_HOURS` — the accumulation window; `tp` at this step is the 0..N h total.
- `MEMBER` — `0` = control, `1..50` = perturbed members.

## Run it interactively (Python console / IPython / JupyterLab)

`uv run` isn't only for whole scripts — it can drop you into an interactive
session with the **same dependencies** already installed, so you can open the
store once and explore it live (slice other variables, dates, members, plot
inline). The trick is `uv run --with <pkg>`: uv builds a throw-away environment
containing those packages and launches whatever command follows. No `pip
install`, no `activate`, nothing to clean up afterwards.

To avoid repeating the long dependency list, set it once:

```bash
DEPS="--with icechunk --with zarr --with xarray --with numpy \
--with gribberish --with s3fs --with matplotlib"
```

**Plain Python console:**

```bash
uv run $DEPS python
```

**IPython console** (nicer REPL — tab-completion, history, `?` help):

```bash
uv run $DEPS --with ipython ipython
```

**JupyterLab** (notebooks in the browser):

```bash
uv run $DEPS --with jupyterlab jupyter lab
```

**Classic Jupyter Notebook**, if you prefer it:

```bash
uv run $DEPS --with notebook jupyter notebook
```

JupyterLab prints a `http://localhost:8888/lab?token=...` URL — open it (it
usually opens automatically). Create a new **Python 3** notebook; it already has
`icechunk`, `xarray`, `gribberish`, `matplotlib`, etc. available. Add
`%matplotlib inline` in a cell to render plots in the notebook. Then paste the
[minimal open below](#the-minimal-open-in-full) into a cell and run it — the
`ds["tp"].isel(...)` slice returns a decoded field you can plot with
`plt.imshow(tp_mm)` right there.

> On a remote/headless machine, add
> `--ServerApp.ip=0.0.0.0 --no-browser` after `jupyter lab` and forward the
> port (e.g. `ssh -L 8888:localhost:8888 user@host`), then open the printed URL
> locally.

> **Reproducibility tip:** the `--with` list above intentionally mirrors the
> `dependencies` block at the top of `demo6_open_icechunk.py`. Keep them in
> sync, or convert this folder into a real `uv` project (`uv init`, then
> `uv add icechunk zarr xarray numpy gribberish s3fs matplotlib jupyterlab`)
> so `uv run jupyter lab` picks the deps up from `pyproject.toml` automatically.

## The minimal open, in full

Everything the demo needs is this — the anonymous open, plus **one line** that
turns a virtual reference into real, decoded bytes:

```python
import icechunk
import xarray as xr
import gribberish.zarr  # noqa: F401 -- registers the "gribberish" Zarr v3 codec

storage = icechunk.s3_storage(
    bucket="e4drr-project",
    prefix="forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd",
    endpoint_url="https://data.source.coop",
    region="us-east-1",
    anonymous=True,        # public read of the store metadata
    from_env=False,        # ignore any AWS_* env vars
    force_path_style=True, # source.coop needs path-style addressing
)

# authorize anonymous byte-range reads of the virtual chunks on AWS
auth = icechunk.containers_credentials(
    {"s3://ecmwf-forecasts/": icechunk.s3_anonymous_credentials()})

# Disable eager manifest preload -- see "Gotchas" below.
cfg = icechunk.RepositoryConfig.default()
cfg.manifest = icechunk.ManifestConfig(
    preload=icechunk.ManifestPreloadConfig(max_total_refs=0, max_arrays_to_scan=0))

repo = icechunk.Repository.open(
    storage, config=cfg, authorize_virtual_chunk_access=auth)
sess = repo.readonly_session("main")

# pick the era you want -- e.g. the current 50r1 stream
ds = xr.open_zarr(sess.store, group="50r1/00z", consolidated=False, zarr_format=3)
print(ds)   # xarray reports the virtual (unrealized) size, e.g. "Size: 169TB"

# total precipitation (metres) for one init date, member, 0-24 h window -> mm
import numpy as np
ti = int(np.argmin(np.abs(ds["time"].values - np.datetime64("2026-05-13"))))
si = int(np.argmin(np.abs(ds["step"].values - 24)))
tp_mm = ds["tp"].isel(time=ti, number=0, step=si).values * 1000.0   # (721, 1440), mm
```

## Gotchas

- **Arrays are under `{era}/00z`, never the root.** Opening the root group is
  empty; opening a bare `era` group is empty too — you need `50r1/00z` etc.
- **`tp` is accumulated, not instantaneous.** `tp` at step *N* is the total
  precipitation over 0..*N* h. Step 0 is all-zero. For a window like 24–48 h,
  subtract: `tp(48h) - tp(24h)`.
- **`tp` is in metres of water-equivalent.** Multiply by 1000 for mm.
- **Variable names can differ by era.** `tp` is present in all three eras, but
  other fields vary (2 m temperature is `t2m` or `2t`; `10u`/`u10`). Probe with
  `next(v for v in candidates if v in ds)` rather than hard-coding.
- **`gribberish.zarr` must be imported** before reading any chunk (it registers
  the Zarr v3 codec) — otherwise even opening a group fails with
  `UnknownCodecError: 'gribberish'` while reading array metadata.
- **`force_path_style=True`** is required for source.coop.
- **`from_env=False`** so stray `AWS_*` env vars don't turn the anonymous read
  into a signed one.
- **Disable eager manifest preload (source.coop sporadic 500s).** source.coop
  returns transient `HTTP 500` ("service error") on a small % of GETs under
  concurrency (this is source.coop, *not* AWS S3, and *not* a rate limit).
  icechunk's default open prefetches thousands of manifests in parallel, so at a
  few-% error rate a *critical* fetch tends to draw a 500 and the open raises
  `IcechunkError: object store error service error`. The
  `ManifestPreloadConfig(max_total_refs=0, max_arrays_to_scan=0)` above turns
  preload off: manifests load lazily on demand (with retry), the stderr noise
  disappears, and open is robust (slower, but reliable). The store itself is
  complete — the errors are transport-side, not missing data.

## Smoke test — all three eras (optional)

To prove the anonymous path works across every schema era (not just `50r1`),
open all three groups and decode a `tp` field from each, asserting physically
sane accumulations. This is the same routine the demo runs, looped over the
eras — drop it in a file and `uv run` it, or paste it into a notebook. Run it
with **no** AWS credentials in the environment:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["icechunk>=2.1","zarr>=3.2","xarray>=2025.1","numpy","gribberish>=1.4","s3fs"]
# ///
import numpy as np, icechunk, xarray as xr, gribberish.zarr  # noqa: F401

storage = icechunk.s3_storage(
    bucket="e4drr-project", prefix="forecasts/ecmwf_ifs_ens_aws_s3_icechunk_vd",
    endpoint_url="https://data.source.coop", region="us-east-1",
    anonymous=True, from_env=False, force_path_style=True)
auth = icechunk.containers_credentials(
    {"s3://ecmwf-forecasts/": icechunk.s3_anonymous_credentials()})
cfg = icechunk.RepositoryConfig.default()
cfg.manifest = icechunk.ManifestConfig(
    preload=icechunk.ManifestPreloadConfig(max_total_refs=0, max_arrays_to_scan=0))
repo = icechunk.Repository.open(storage, config=cfg, authorize_virtual_chunk_access=auth)
sess = repo.readonly_session("main")

fails = []
for era in ["0p4", "49r1", "50r1"]:
    ds = xr.open_zarr(sess.store, group=f"{era}/00z", consolidated=False, zarr_format=3)
    var = next(v for v in ("tp", "tprate") if v in ds)
    si = int(np.argmin(np.abs(ds["step"].values - 24))); step = int(ds["step"].values[si])
    ti = int(np.argmax(ds["time"].values))
    init = np.datetime_as_string(ds["time"].values[ti], unit="D")
    mm = ds[var].isel(time=ti, number=0, step=si).values * 1000.0
    finite = float(np.isfinite(mm).mean()); mean = float(np.nanmean(mm)); mx = float(np.nanmax(mm))
    ok = finite > 0.99 and 0 <= mean < 50 and mx < 2000
    print(f"  [{'PASS' if ok else 'FAIL'}] {era:<4} {var} 0-{step}h @ {init} -- "
          f"shape {mm.shape}, mean {mean:.2f} mm, max {mx:.1f} mm, finite {finite:.3f}")
    if not ok: fails.append(era)

print("RESULT:", "PASS -- anonymous open + virtual tp decode works for all eras"
      if not fails else f"FAIL -- {fails}")
raise SystemExit(0 if not fails else 1)
```

Expected tail:

```
  [PASS] 0p4  tp 0-24h @ 2024-02-28 -- shape (451, 900), mean 2.34 mm, max 210.7 mm, finite 1.000
  [PASS] 49r1 tp 0-24h @ 2026-05-12 -- shape (721, 1440), mean 2.52 mm, max 228.5 mm, finite 1.000
  [PASS] 50r1 tp 0-24h @ 2026-07-02 -- shape (721, 1440), mean 2.85 mm, max 291.0 mm, finite 1.000
RESULT: PASS -- anonymous open + virtual tp decode works for all eras
```
