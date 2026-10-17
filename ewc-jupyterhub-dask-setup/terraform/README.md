# Terraform: one JupyterHub gateway

Manages a single gateway end to end — floating IP, persistent state volume, the
VM, and the DNS record at the CDN. Rebuilding the VM keeps DNS correct and
preserves user accounts, notebooks and the TLS certificate.

Scope is deliberately one gateway. Workers and any second gateway stay
CLI-managed (see `../OPENSTACK-CLI.md`): they hold no state, so the bookkeeping
Terraform provides buys little, and a smaller blast radius is worth more while
learning the platform.

## Why Terraform for this, and not for a lone DNS record

The A record depends on the floating IP, and the VM depends on the volume.
Terraform expresses that ordering and re-applies it on every rebuild. For a
single standalone DNS record a shell script would be simpler — the dependency
is what justifies the tool.

## Lifecycle split

| Resource | Lifecycle | On VM rebuild |
|---|---|---|
| Floating IP | persistent (`prevent_destroy`) | unchanged, DNS stays valid |
| State volume | persistent (`prevent_destroy`) | reattached, data intact |
| Instance | disposable | replaced in ~2 min |
| DNS record | follows the floating IP | unchanged |

State volume holds:

```
/srv/state/ssl/cloudflare/   -> /etc/ssl/cloudflare          (TLS cert + key)
/srv/state/jupyterhub/       -> /srv/jupyterhub              (user DB, cookie secret)
/srv/state/userhomes/        -> /var/lib/private/jupyterhub-singleuser
```

The TLS private key therefore never enters `terraform.tfstate` or cloud-init
`user-data` (both readable — the latter via the metadata service, by any Hub
user with a terminal).

## Prerequisites

**1. Cloudflare API token** — https://dash.cloudflare.com/profile/api-tokens →
Create Token → Custom token:

| Field | Value |
|---|---|
| Permissions | Zone · DNS · **Edit** |
| Zone Resources | Include · Specific zone · `example.org` |
| Client IP Filtering | your workstation IP (recommended) |
| TTL | set an expiry |

Summary must read *"Edit DNS for example.org"*. **Never the Global API
Key** — account-wide, unscopeable, unrevocable without rotating everything.

**2. `terraform.tfvars`** (git-ignored):

```hcl
cf_api_token = "..."
```

**3. OpenStack auth** — `~/.config/openstack/clouds.yaml`, entry `openstack`.

## Adopting the existing gateway

The gateway already exists, so **import before applying** or Terraform will try
to create a second one.

```bash
terraform init
```

Add temporarily to `main.tf`:

```hcl
import {
  to = openstack_networking_floatingip_v2.gw2
  id = "cde72844-734b-482d-b9cc-4e424ea9bd4c"
}
import {
  to = openstack_compute_instance_v2.gw2
  id = "935b9070-d2a1-41fd-a6e0-062ce215f751"
}
```

```bash
terraform plan
```

> ⚠️ The plan **will** show the instance being replaced, because `user_data`
> differs from what the running VM was built with (it now mounts a state
> volume). That replacement is the migration — do the backup below first.

## Migration (once)

The running gateway keeps its state on the root disk. Preserve it before the
first apply:

```bash
ssh ubuntu@<gateway-floating-ip> "sudo tar czf - -C / srv/jupyterhub etc/ssl/cloudflare var/lib/private/jupyterhub-singleuser 2>/dev/null" > gw2-state.tgz
```
```bash
tar tzf gw2-state.tgz | head
```

Then `terraform apply`, and restore onto the new volume:

```bash
scp gw2-state.tgz ubuntu@<gateway-floating-ip>:/tmp/
```
```bash
ssh ubuntu@<gateway-floating-ip> "sudo tar xzf /tmp/gw2-state.tgz -C /srv/state --strip-components=0 && sudo systemctl restart jupyterhub"
```

⚠️ Check paths land under `/srv/state/{jupyterhub,ssl,userhomes}` — the bind
mounts expect that layout.

From then on, rebuilds need no migration:

```bash
terraform apply -replace=openstack_compute_instance_v2.gw2
```

## Routine use

```bash
terraform plan                 # always read before applying
terraform apply
terraform output url
```

Change per-user memory or concurrency by editing `terraform.tfvars`:

```hcl
gw2_mem_limit        = "4G"
gw2_concurrent_users = 7
```

`apply` then replaces the VM (~2 min) with state intact.

## State file

Local state is fine here: single operator, no secrets in state (certificates
live on the volume). Requirements:

- Never commit: `terraform.tfstate*`, `.terraform/`, `*.tfvars`
- Back it up: `cp terraform.tfstate ~/backups/tfstate-$(date +%F).json`
- Losing it destroys nothing — resources live in OpenStack. Re-establish with
  `terraform import`. The real hazard is *stale* state, where Terraform creates
  a duplicate or edits something gone: always read `plan` before `apply`.

The OpenStack CLI remains the source of truth and the fallback for anything
urgent.

## Not automated, deliberately

**Origin certificates.** The Cloudflare provider *can* issue them
(`cloudflare_origin_ca_certificate`), but the private key would then sit in
`terraform.tfstate` and reach the VM via `user-data`. Certificates are valid 15
years and one certificate can cover all gateways
(`*.example.org`), so automation saves a handful of manual actions ever and
costs a meaningful exposure. Install once onto the volume:

```bash
sudo nano /srv/state/ssl/cloudflare/origin.pem
sudo nano /srv/state/ssl/cloudflare/origin.key
sudo chmod 600 /srv/state/ssl/cloudflare/origin.key
sudo systemctl reload nginx
```

Also set **SSL/TLS → Overview → Full (strict)** on the zone, *after* the real
certificate is in place — before that Cloudflare returns **526**.
