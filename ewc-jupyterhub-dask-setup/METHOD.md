# Running JupyterHub and a Dask cluster on the European Weather Cloud

How a small team was given browser-based access to ECMWF's European Weather
Cloud (EWC) — with a shared Dask cluster behind it — without Kubernetes, and
without any team member ever handling a cloud credential.

Written for people facing the same problem. No credentials, keys, addresses or
tenancy identifiers appear here; placeholders are used throughout.

---

## 1. The problem

A team of **7 analysts** needed to work on forecast data held in EWC object
storage. Most had no SSH experience, and the work involved datasets far larger
than a laptop.

The requirements that shaped everything:

- Users work in a **browser**. No SSH, no CLI, no local installation.
- Users **never receive cloud credentials**. One leaked key compromises the
  whole tenancy.
- Heavy computation must not run in the notebook, which has to stay small.
- An administrator should be able to rebuild any machine in minutes.

## 2. Does a Dask cluster need Kubernetes?

Usually the answer given is yes — Zero-to-JupyterHub on Kubernetes, with
Dask Gateway or `dask-kubernetes` alongside. That is the right answer for some
deployments and the wrong one for many, and the deciding factors are not about
Dask at all.

**Kubernetes earns its place when:**

- User numbers are large or unpredictable, and nodes must scale automatically.
- Users need genuinely different environments, which containers isolate cleanly.
- Clusters are created and destroyed per user or per job, rather than running as
  one shared pool.
- The team already operates Kubernetes for other things, so the cluster is not
  an additional thing to learn and maintain.

**Plain VMs are usually better when:**

- The user count is small and known, and a fixed pool is sufficient.
- Everyone shares one environment.
- The allocation is fixed-term, so time spent on platform is time not spent on
  science.
- Nobody on the team operates Kubernetes day to day.

| | Kubernetes | Plain VMs |
|---|---|---|
| Moving parts | cluster, ingress, storage classes, Helm charts | VMs, systemd, a reverse proxy |
| Time to first working Hub | days | hours |
| Per-user isolation | containers | systemd units + cgroups |
| Scaling | automatic | manual, by creating VMs |
| Skills to operate | Kubernetes | Linux |
| Rebuild after a mistake | involved | ~2 minutes per VM |

**The isolation question is the one most often got wrong.** Kubernetes is
frequently chosen for per-user resource limits — but systemd provides the same
guarantee on an ordinary VM. `SystemdSpawner` runs each notebook server as its
own transient unit with a cgroup memory limit, a private `/tmp` and no sudo. A
user who exceeds their limit gets a `MemoryError` in their own kernel; nobody
else is affected.

> Whichever you choose, verify enforcement rather than trusting configuration:
> `systemctl show jupyter-<user> -p MemoryMax` must return a byte count. Several
> spawners accept the same `mem_limit` setting and only *display* it — the
> number appears in the user's interface while nothing enforces it, and the
> first sign of trouble is one user's runaway job killing another's.

What a shared Dask cluster actually needs is simpler than either option: a
scheduler the workers can reach, workers with matching package versions, and a
network boundary around them. None of that requires an orchestrator.

The deployment documented here took the plain-VM route: a fixed-term
allocation, a known handful of users, one shared environment, and no Kubernetes
experience on the team. A long-lived service with fluctuating demand should
weigh it differently.

## 3. Architecture

```
            Users (browser only)
                    │
            CDN / reverse proxy, TLS
                    │
   ┌────────────────┴────────────────┐
   │                                 │
 Gateway A                        Gateway B
 JupyterHub + Dask scheduler      JupyterHub
 8 vCPU / 32 GB                   8 vCPU / 32 GB
   │                                 │
   └──────────────┬──────────────────┘
                  │  private network only
        ┌─────────┴──────────┐
        │  6 × Dask worker   │
        │  4 vCPU / 16 GB    │
        │  no public address │
        └────────────────────┘
```

Two gateways rather than one because the largest flavour available was 32 GB,
and per-user memory times concurrent users has to fit inside it. Splitting the
team across two Hubs doubled capacity.

**Only the gateways are publicly reachable.** Workers have no public address and
reach the internet through the tenancy router's NAT.

### Sizing

| | Per user | Concurrent | Total |
|---|---|---|---|
| Notebook memory | 8 GB | 3 per gateway | 48 GB |
| Dask workers | — | 6 | ~84 GB usable |

Workers self-size at boot from `nproc` and `free`, reserving ~2 GB for the OS,
so the same image works on any flavour. Per worker: 1 process, 4 threads, 14 GB.

> The notebook is a remote control, not the engine. Small notebooks are a
> feature: they force work onto the cluster, where there is six times the
> memory. Raising the notebook limit treats the symptom and costs everyone a
> concurrency slot.

## 4. TLS and the edge proxy — not optional

JupyterHub binds to **loopback only**. Nothing it serves is encrypted, and
nothing reaches it directly. TLS is terminated in front of it, and the way that
is arranged turns out to matter more than it first appears.

```
browser ──TLS──▶ CDN edge ──TLS──▶ nginx :443 ──▶ proxy :8000 ──▶ Hub :8081
                 (public cert)      (origin cert)   (loopback)      (loopback)
```

A CDN in front of the gateway earns its place for four reasons:

- **Certificates without renewal machinery.** The edge presents a managed public
  certificate. The origin uses a long-lived *origin certificate*, valid for
  years, trusted only by that CDN. No ACME client, no renewal cron to fail
  silently after an allocation ends.
- **No challenge port.** Certificate issuance needs no inbound HTTP, so port 80
  is never exposed for validation.
- **The origin address is hidden.** DNS resolves to the CDN, not to the VM, so
  the machine is not trivially discoverable by scanning.
- **One name per gateway**, which users can remember and which survives the VM
  being rebuilt — the address stays attached, the name never changes.

### Use strict origin validation

Set the CDN's TLS mode to the strictest option — one that validates the origin
certificate.

> ⚠ A "flexible" mode, which encrypts browser-to-edge but speaks **plain HTTP to
> the origin**, is the dangerous default to avoid. Users see a padlock while
> passwords cross the public internet in clear text. With a self-hosted user
> database, that is a credential-harvesting exposure wearing a reassuring icon.

Expect an error (commonly **526**) between enabling strict mode and installing
the origin certificate. That is the mode working correctly, not a fault.

### Two configuration traps

**Websockets must pass through.** JupyterLab uses them for every kernel message.
Without the upgrade headers the interface loads and then hangs on a spinning
indicator — which reads as a broken kernel, not a proxy problem:

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400;
```

**Tell the Hub its public URL.** This one is worth reading twice; it caused
two outages here and an initial misdiagnosis. The chain is CDN → nginx → JupyterHub's own proxy → Hub. nginx
correctly sets `X-Forwarded-Proto: https`, but the intermediate proxy *appends*
`http` for its own plaintext hop, producing `https,http`. The Hub reads the last
value, concludes the request is insecure, and issues session cookies **without
the `Secure` flag** — which browsers then refuse to send back. Every login and
signup fails with a cross-site-request-forgery error that points nowhere near
the real cause.

```python
c.JupyterHub.public_url = "https://hub.example.org"
```

The tell is in the Hub log: `Skipping XSRF check for insecure request`. From
outside, the session cookie arrives without `Secure`. Both are easy to confirm
and neither is obvious if you are looking at the authenticator.


## 5. Cloud credentials: how EWC access actually works

EWC authenticates humans through federated identity (institutional SSO). There
is no password an API client can use. Programmatic access therefore uses an
**application credential**, created once through the web console.

```yaml
# ~/.config/openstack/clouds.yaml
clouds:
  mycloud:
    auth_type: v3applicationcredential
    auth:
      auth_url: https://<keystone-endpoint>/v3
      application_credential_id: "..."
      application_credential_secret: "..."
    region_name: "..."
    interface: public
    identity_api_version: 3
```

```bash
pip install python-openstackclient
export OS_CLOUD=mycloud
openstack limits show --absolute      # verify
```

Four things worth knowing before you start:

**The downloaded `clouds.yaml` needs editing.** The console generates it for
password authentication, including `project_name`, `project_id`, `username` and
`user_domain_name`. An application credential is already scoped to its project
and user, so these are redundant — and `project_name` triggers a domain
resolution that fails with a confusing message about `project_domain_id`.
Delete all four.

**Verify with `limits show`, not `token issue`.** The latter prints a live token
into your terminal and shell history.

**Roles matter.** Creating the credential with a narrowed role produces one that
authenticates but cannot list servers. Leave the roles field blank to inherit
your project roles.

**⚠ Expiry is the single biggest operational hazard.** Application credentials
expire. When one does, the platform *keeps serving users* while all management
access stops — so nobody notices until something needs doing. We were caught by
this four times. Record the expiry date and set a reminder before it.

### Credentials cannot mint credentials

By default an application credential is forbidden from creating further
credentials:

```
Using method 'application_credential' is not allowed for managing additional
application credentials. (HTTP 403)
```

This is a feature: it means a credential handed to a colleague cannot be used to
escalate. When you genuinely need to mint another kind of credential, create a
temporary *unrestricted* one through the console, use it once, and delete it
immediately.

> Never leave an unrestricted credential as your working credential. We did,
> briefly, and deleting it later cut off all management access.

## 6. How users get in — no credentials, by design

**Team members never receive a cloud credential.** They receive a URL.

JupyterHub's `NativeAuthenticator` keeps its own user database: people sign up
with a username and password of their choosing. Two settings make this workable:

```python
c.NativeAuthenticator.open_signup = False          # admin approves
c.Authenticator.allowed_users = {"alice", "bob"}   # these skip approval
c.Authenticator.allow_all = True                   # required on JupyterHub 5
```

Pre-listing the known cohort in `allowed_users` means they sign up and are in
immediately — no approval step, no waiting on an administrator. Anyone *not*
listed lands in an approval queue, so the page stays closed to strangers.

> Pending signups appear at `/hub/authorize`, **not** `/hub/admin`. Nothing
> notifies the administrator that someone is waiting. Pre-listing avoids the
> problem entirely; without it, somebody must remember to check.

Agree a username convention in the invitation — lower case, no spaces — or the
allowlist will not match what people type.

### What users are told

1. Their URL (one only — the two Hubs have separate user databases, so an
   account on one does not exist on the other).
2. **Log out when finished**, rather than closing the tab. Concurrency slots are
   limited and a closed tab holds one until the idle culler reclaims it.
3. Heavy work goes to the cluster, not the notebook.
4. **The date the allocation ends**, at signup — not in the final week.

## 7. The Dask cluster

A scheduler on one gateway, six workers on the private network. Workers connect
outbound to the scheduler; nothing connects inward.

```ini
[Service]
ExecStart=/opt/env/bin/dask worker tcp://<scheduler>:8786 \
  --nworkers 1 --nthreads 4 --memory-limit 14000MB \
  --local-directory /scratch/dask --death-timeout 120
Restart=always
```

**⚠ The scheduler port has no authentication.** Anything that can reach it can
execute arbitrary Python on every worker. This is the single most important
security property of the design:

- Workers and scheduler sit on a private network with no public addresses.
- Firewall rules are scoped **to the security group itself**, not to an IP
  range, so only cluster members can connect.
- The dashboard is exposed to users through the authenticated Hub session
  (via `jupyter-server-proxy`), never as an open port.

Two things that are easy to get wrong:

**Open the worker-to-worker port range, not just the scheduler port.** Dask
shuffles connect workers directly to each other. Without the ephemeral range,
small jobs succeed and large ones hang — which looks like a performance problem,
not a firewall one.

**Pin package versions identically across client, scheduler and workers.**
Version skew surfaces as opaque deserialization errors, not a clear message.
Pin the transitive dependencies too: `msgpack` and `tornado` drifted between a
gateway built in one month and workers rebuilt the next, because only the
top-level packages were pinned.

## 8. Object storage credentials — the part worth copying

The cluster reads and writes object storage. How those credentials reach the
workers is the most consequential decision in the whole setup.

**The approach taken here, which is the weakest part of this design:** a
long-lived object-store key baked into each worker's cloud-init. It works, but rotating it means rebuilding every worker,
and any Hub user can read it — `client.run()` executes arbitrary code on
workers, so a credential present on a worker is a credential shared with every
user of the cluster.

**Better, where the platform supports it:** attach an *identity* to the machine
rather than a secret. On clouds offering instance-attached service accounts, the
library fetches short-lived tokens from a metadata service. Nothing to place,
nothing to leak, nothing to rotate.

**For short-lived tokens, pass them at call time.** Some providers issue
credentials valid for hours. Baking those into a VM guarantees breakage. Instead
the driver holds them and passes them into tasks as arguments — they travel with
the work, in memory, and never touch worker disk:

```python
creds = {k: os.environ[k] for k in ("ACCESS_KEY", "SECRET_KEY", "SESSION_TOKEN")}
futures = client.map(do_work, items, creds=creds)
```

**And check whether you need credentials at all.** Public datasets are usually
readable anonymously. We once debugged an expired token for a read that never
required one.

> A useful diagnostic: distinguish *404 / NoSuchBucket* from *403 /
> AccessDenied*. The first means the name is wrong; the second means the name is
> right and you lack permission. Confusing them sends you looking in entirely
> the wrong place.

## 9. Operational lessons

**Reproducibility beats backups.** Every machine is defined by a cloud-init
file in version control. A broken VM is deleted and rebuilt in ~2 minutes rather
than repaired. This only works if changes go into the file, not onto the
machine. Several fixes here were applied live and existed nowhere else until a
later audit found them missing from the definitions.

**Separate persistent from disposable.** State that must survive — TLS material,
the user database, notebooks — belongs on an attached volume, not the root disk.
Without it, every rebuild loses user accounts and work.

**A green deployment is not a working system.** Infrastructure tooling reported
success while a floating address was attached to nothing, and while a volume
silently failed to mount and state went to the root disk. Both were invisible
until something downstream failed. Check the thing itself: `df`, a real HTTP
request, an actual login.

**Keep a negative control in every connectivity test.** A probe that reports a
port open is worthless unless a port you know is closed reports closed. We
raised a false security alarm on a test without one.

**Idle timeouts measure the wrong thing.** JupyterHub's culler tracks notebook
activity, not cluster activity. Work submitted asynchronously leaves the kernel
idle while workers are saturated — and the culler then kills the client
mid-computation, cancelling everything in flight. Set the timeout to span a
working day, and run long jobs detached from the notebook session entirely.

**Processes started in a browser terminal do not outlive the session.** Under
`SystemdSpawner` they share the user server's cgroup and are killed with it —
`tmux` and `nohup` included. Long jobs need their own systemd unit.

## 10. What this cost

| | |
|---|---|
| Users served | 7 |
| VMs | 2 gateways + 6 workers |
| Cluster memory | ~84 GB |
| Time to first working Hub | about a day |
| Ongoing administration | user approvals; credential renewal |

No Kubernetes, no container registry, no Helm. Two reverse-proxied VMs and six
workers, each defined by a file.

The honest summary: the hard parts were never Dask or JupyterHub. They were
credential lifetimes, the difference between configured and enforced, and
resisting the urge to fix a machine instead of its definition.
