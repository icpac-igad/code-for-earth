# JupyterHub + Dask on the European Weather Cloud

Everything needed to give a small team browser-based access to ECMWF's European
Weather Cloud, backed by a shared Dask cluster — **without Kubernetes**, and
without any team member handling a cloud credential.

This is the infrastructure the other demos run on. Where the other demos in this repository show what to
compute, this shows where to compute it.

## Contents

| | |
|---|---|
| [`METHOD.md`](METHOD.md) | **Start here.** The reasoning: why not Kubernetes, how credentials work, how users get in, what went wrong |
| [`OPENSTACK-CLI.md`](OPENSTACK-CLI.md) | Provisioning from the CLI: `clouds.yaml`, application credentials, `openstack server create` |
| [`cloud-init/`](cloud-init/) | Machine definitions — gateway, worker, pinned environment |
| [`terraform/`](terraform/) | Declarative build of one gateway, with persistent state and DNS |
| [`scripts/`](scripts/) | Cluster verification and two JupyterHub fixes |

## What it builds

```
            Users (browser only)
                    │
            CDN edge, TLS terminated
                    │
   ┌────────────────┴────────────────┐
 Gateway A                        Gateway B
 JupyterHub + Dask scheduler      JupyterHub
   │                                 │
   └──────────────┬──────────────────┘
                  │  private network only
        ┌─────────┴──────────┐
        │  6 × Dask worker   │
        │  no public address │
        └────────────────────┘
```

Two gateways at 8 vCPU / 32 GB, six workers at 4 vCPU / 16 GB, ~84 GB of
cluster memory, serving 7 users. Built in about a day.

## Design decisions worth borrowing

**No Kubernetes.** `SystemdSpawner` gives each user's notebook its own systemd
unit with a **cgroup-enforced** memory limit, private `/tmp` and no sudo. The
isolation Kubernetes is usually chosen for, without the cluster.

> Verify enforcement rather than trusting it:
> `systemctl show jupyter-<user> -p MemoryMax` must return a byte count. Under
> some spawners the same setting is advisory — shown to the user, enforced by
> nothing.

**Users never receive a cloud credential.** They get a URL. JupyterHub holds its
own user database; pre-listing the cohort in `allowed_users` means they sign up
and are in, with no administrator in the loop.

**The Dask scheduler port has no authentication.** Anything that reaches it runs
arbitrary Python on every worker. Workers therefore have no public address, and
firewall rules are scoped to the security group rather than to an IP range.

**Machines are disposable; state is not.** Every VM is defined by a file here. A
broken machine is deleted and rebuilt in ~2 minutes. State that must survive —
TLS material, the user database, notebooks — lives on an attached volume.

## Quickstart

```bash
pip install python-openstackclient
export OS_CLOUD=<your-cloud>
openstack limits show --absolute          # verify credentials
```

Create a gateway, substituting your own hostname and admin username first:

```bash
openstack server create --image "Ubuntu-22.04" --flavor <8cpu-32gb-flavor> \
  --network <your-private-network> --security-group <gateway-sg> \
  --key-name <your-keypair> --user-data cloud-init/gateway.yaml --wait hub-a
```

Then workers, substituting the scheduler's private address:

```bash
sed 's|${SCHEDULER_IP}|<scheduler-private-ip>|' cloud-init/worker.yaml > /tmp/w.yaml
for i in 01 02 03 04 05 06; do
  openstack server create --image "Ubuntu-22.04" --flavor <4cpu-16gb-flavor> \
    --network <your-private-network> --security-group <cluster-sg> \
    --key-name <your-keypair> --user-data /tmp/w.yaml dask-worker-$i
done
```

Verify:

```bash
python scripts/test-dask-cluster.py
```

Full detail, including TLS and the security groups, is in
[`OPENSTACK-CLI.md`](OPENSTACK-CLI.md) and [`METHOD.md`](METHOD.md).

## Placeholders

Every tenancy-specific value is a placeholder. Replace before use:

| Placeholder | Meaning |
|---|---|
| `hub-a.example.org` | your gateway hostname |
| `<your-private-network>` | tenancy private network |
| `<scheduler-private-ip>` | gateway A's private address |
| `<your-bucket>` | object-store bucket |
| `<your-keypair>` | SSH keypair name |
| `admin-username`, `alice`… | JupyterHub usernames |

**No credentials, keys or addresses appear anywhere in this folder**, and none
should be added. `cloud-init/worker.yaml` carries `REPLACE_ME` where an object
store key would go — see `METHOD.md` §8 for why putting one there is the weakest
part of this design and what to do instead.

## Caveats

⚠ **This is a time-boxed allocation pattern.** User notebooks live on the
gateways. Tell users the end date when they sign up, not in the final week.

⚠ **Application credentials expire**, and when they do the platform keeps
serving users while all management access stops — so nobody notices. Record the
expiry date.

⚠ **Pin transitive dependencies**, not just top-level packages. Dask reports
client/scheduler/worker version skew as opaque deserialization errors.
