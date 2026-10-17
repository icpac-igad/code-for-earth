# Provisioning EWC VMs from the CLI (no GUI)

End-to-end OpenStack CLI path: mint credentials once, then create, access and
tear down VMs entirely from the terminal.

**Bootstrap caveat:** EWC authenticates via federated IAM (ECMWF/EUMETSAT SSO),
so there is no Keystone username/password the CLI can use directly. You must
visit Horizon **once** to create an application credential. Everything after
that is CLI-only.

---

## 1. Install the client

```bash
python3 -m venv ~/.venvs/openstack
source ~/.venvs/openstack/bin/activate
pip install python-openstackclient python-novaclient python-neutronclient
```

## 2. Mint the application credential (one-time, in Horizon)

Horizon → **Identity → Application Credentials → Create Application Credential**

| Field | Value |
|---|---|
| Name | `cli-provisioning` |
| Roles | leave blank to inherit your roles, or pick `member` to scope down |
| Expiration | set one — e.g. 6 months |
| Access Rules | optional; see §7 for a locked-down delegate credential |
| Unrestricted | **leave unchecked** |

The `id` and `secret` are shown **once**. Copy both.

Horizon also offers a ready-made download: **"Download clouds.yaml"** on that
same confirmation screen. That file already contains the correct `auth_url`,
`project_id` and region for your tenancy — use it instead of hand-writing §3.

## 3. Configure `clouds.yaml`

```bash
mkdir -p ~/.config/openstack
chmod 700 ~/.config/openstack
```

`~/.config/openstack/clouds.yaml`:

```yaml
clouds:
  openstack:                                  # name it what you like; must match $OS_CLOUD
    auth_type: v3applicationcredential
    auth:
      auth_url: https://auth.os-api.<region>.ecmwf.int
      application_credential_id: "<id>"
      application_credential_secret: "<secret>"
    region_name: "RegionOne"
    interface: public
    identity_api_version: 3
```

⚠️ **Do not include `project_name`, `project_id`, `username`, or
`user_domain_name` under `auth:`.** An application credential is already scoped
to its project and user, so those fields are redundant — and `project_name`
triggers domain resolution that fails with:

> You have provided a project_name. In the V3 identity API a project_name is
> only unique within a domain so you must also provide either a
> project_domain_id or project_domain_name.

The `clouds.yaml` that Horizon generates **does** include them (it is written
for password auth). Strip them after downloading.

```bash
chmod 600 ~/.config/openstack/clouds.yaml   # it holds a live secret
export OS_CLOUD=openstack                    # must match the key above
openstack limits show --absolute             # verify: prints your quota
```

Prefer `limits show` over `token issue` to verify — it confirms authentication
without printing a live token to your terminal and shell history.

If `openstack: command not found` after a successful `pip install`, the client
is installed in a different environment than the active one. Locate and
activate it **by path**, which is unambiguous when several envs share a name:

```bash
find ~ /srv -maxdepth 6 -name openstack -type f -path '*/bin/*' 2>/dev/null
micromamba activate /full/path/to/env
```

Alternative without a file on disk — env vars, e.g. sourced from a password
manager so the secret never touches the filesystem:

```bash
export OS_AUTH_TYPE=v3applicationcredential
export OS_AUTH_URL=https://<<your-keypair>stone-endpoint>/v3
export OS_APPLICATION_CREDENTIAL_ID=$(pass show ewc/cred-id)
export OS_APPLICATION_CREDENTIAL_SECRET=$(pass show ewc/cred-secret)
export OS_REGION_NAME=<region>
export OS_IDENTITY_API_VERSION=3
```

## 4. Discover what you can build on

```bash
openstack image list --status active
openstack flavor list
openstack network list
openstack security group list
openstack limits show --absolute        # your quota headroom
```

Pick an Ubuntu 22.04 image, a flavor matching the sizing you need, and your
tenancy's private network.

## 5. Keypair and security groups

```bash
# Register an existing public key (preferred - the private key never moves)
openstack keypair create --public-key ~/.ssh/id_ed25519.pub <your-keypair>

# Or have OpenStack generate one (private key printed once, to stdout)
openstack keypair create <your-keypair> > ~/.ssh/<your-keypair>.pem && chmod 600 ~/.ssh/<your-keypair>.pem
```

Gateway group — public-facing, HTTP/HTTPS only. Add SSH from your own IP, not
from `0.0.0.0/0`:

```bash
openstack security group create gw-web --description "JupyterHub gateway"
openstack security group rule create --proto tcp --dst-port 80  --remote-ip 0.0.0.0/0 gw-web
openstack security group rule create --proto tcp --dst-port 443 --remote-ip 0.0.0.0/0 gw-web
openstack security group rule create --proto tcp --dst-port 22 --remote-ip <your.ip>/32 gw-web
```

Dask group — private network only, never exposed to a floating IP:

```bash
openstack security group create dask-internal --description "Dask scheduler/worker"
openstack security group rule create --proto tcp --dst-port 8786 \
  --remote-group dask-internal dask-internal      # scheduler comms
openstack security group rule create --proto tcp --dst-port 8787 \
  --remote-group dask-internal dask-internal      # dashboard
openstack security group rule create --proto tcp --dst-port 1024:65535 \
  --remote-group dask-internal dask-internal      # worker-to-worker shuffles
```

`--remote-group` restricts traffic to members of that same group, which is what
keeps these ports off the wider network.

## 6. Create the VM with cloud-init

Substitute the placeholders in the cloud-init file first — they are literal
text, not shell variables:

```bash
sed -e 's|PUBLIC_HOSTNAME|jupyter.example.org|' \
    -e 's|ADMIN_USER|yourname|' \
    -e 's|ADMIN_EMAIL|you@example.org|' \
    cloud-init-jupyterhub-gateway.yaml > /tmp/gateway.yaml
```

Gateway:

```bash
openstack server create \
  --image "Ubuntu-22.04" \
  --flavor "<8vcpu-64gb-flavor>" \
  --network "<private-net>" \
  --security-group gw-web \
  --security-group dask-internal \
  --key-name <your-keypair> \
  --user-data /tmp/gateway.yaml \
  --wait \
  jupyterhub-gateway
```

Floating IP — only this VM gets one:

```bash
openstack floating ip create <external-net>
openstack server add floating ip jupyterhub-gateway <floating-ip>
```

Dask workers — no floating IP, private group only:

```bash
sed 's|${SCHEDULER_IP}|10.0.0.X|' cloud-init-dask-worker.yaml > /tmp/worker.yaml

for i in $(seq -w 1 8); do
  openstack server create \
    --image "Ubuntu-22.04" \
    --flavor "<4vcpu-16gb-flavor>" \
    --network "<private-net>" \
    --security-group dask-internal \
    --key-name <your-keypair> \
    --user-data /tmp/worker.yaml \
    dask-worker-$i
done
```

Scratch volume per worker (see the worker cloud-init's `/dev/vdb` handling):

```bash
openstack volume create --size 100 dask-scratch-01
openstack server add volume dask-worker-01 dask-scratch-01
```

## 7. Lifecycle and verification

```bash
openstack server list
openstack server show jupyterhub-gateway
openstack console log show jupyterhub-gateway     # watch cloud-init progress
openstack console url show jupyterhub-gateway     # browser console, no SSH

openstack server stop  dask-worker-01
openstack server start dask-worker-01
openstack server reboot dask-worker-01
openstack server delete dask-worker-01
```

⚠️ `openstack server delete` does not prompt. Confirm the name first with
`openstack server show`.

## 8. Managing credentials from the CLI

Once bootstrapped, further credentials need no GUI:

```bash
openstack application credential list
openstack application credential show <name>

# Scoped delegate credential - create/stop/list servers only
openstack application credential create delegate-vm-ops \
  --role member \
  --expiration "2026-12-31T00:00:00" \
  --access-rules '[
    {"service": "compute", "method": "POST", "path": "/v2.1/servers"},
    {"service": "compute", "method": "POST", "path": "/v2.1/servers/*/action"},
    {"service": "compute", "method": "GET",  "path": "/v2.1/servers*"}
  ]'

openstack application credential delete <name>    # immediate revocation
```

**Constraint:** an application credential created with `unrestricted: false`
(the default, and the recommended setting) **cannot create further application
credentials or Keystone trusts**. Only your own federated IAM login can mint
them. So the bootstrap in §2 is always done by the account owner, and delegates
cannot self-service additional credentials.

## 9. Hygiene

- Set an expiration on every credential; rotate before it lapses.
- One credential per person or per automation, so revoking one doesn't disrupt
  the others.
- `chmod 600` on `clouds.yaml`; never commit it. Add to `.gitignore`.
- Terraform state also stores the secret — encrypt state or keep it local.
- Revoke immediately with `application credential delete` if a secret leaks;
  there is no rotate-in-place.
