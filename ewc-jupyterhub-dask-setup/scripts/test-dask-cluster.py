"""
Dask cluster smoke test - paste into a JupyterHub notebook cell.

Works from either Hub: DASK_SCHEDULER_ADDRESS is preset by the spawner
(127.0.0.1:8786 on gateway 1, <scheduler-private-ip>:8786 on gateway 2).

Proves three things:
  1. the scheduler is reachable and workers are registered
  2. work is actually distributed across the 6 worker VMs, not run locally
  3. the cluster can process far more data than the notebook's own RAM cap
"""

import os
import socket
from dask.distributed import Client

# ---------------------------------------------------------------- 1. connect
client = Client(os.environ.get("DASK_SCHEDULER_ADDRESS", "tcp://127.0.0.1:8786"))
print(client)

info = client.scheduler_info()["workers"]
total_threads = sum(w["nthreads"] for w in info.values())
total_mem_gb = sum(w["memory_limit"] for w in info.values()) / 1e9

print(f"\nworkers        : {len(info)}")
print(f"total threads  : {total_threads}")
print(f"total memory   : {total_mem_gb:.0f} GB")
print(f"notebook host  : {socket.gethostname()}")

print("\nregistered workers:")
for addr, w in sorted(info.items()):
    print(f"  {w['host']:<16} {w['nthreads']} threads  "
          f"{w['memory_limit']/1e9:.0f} GB  ({w['name']})")

# --------------------------------------------- 2. prove work leaves this VM
# Each task reports the hostname that executed it. If the cluster is wired up
# correctly these are the dask-worker-* VMs, NOT the notebook's own host.
hosts = client.run(socket.gethostname)
print("\nhosts executing tasks:")
for addr, host in sorted(hosts.items(), key=lambda kv: kv[1]):
    print(f"  {host}")

distinct = set(hosts.values())
assert socket.gethostname() not in distinct, "work is running locally, not on the cluster"
print(f"\nOK: work is distributed across {len(distinct)} separate worker VMs")

# ------------------------------------- 3. compute on more data than fits here
# ~24 GB array: far beyond the 8 GB (or 4 GB) notebook cap, so this can only
# succeed if the computation really happens on the worker pool.
import dask.array as da

# Square, because x.T below requires matching shapes for the addition.
x = da.random.random((55_000, 55_000), chunks=(5_000, 5_000))
print(f"\narray size     : {x.nbytes / 1e9:.1f} GB")
print(f"chunks         : {len(x.chunks[0]) * len(x.chunks[1])}")

result = (x + x.T).mean().compute()
print(f"result         : {result:.6f}   (expect ~1.0)")

print("\nCLUSTER OK")
