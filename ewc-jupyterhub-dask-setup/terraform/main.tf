/*
 * EWC JupyterHub gateway 2 - trimmed Terraform build.
 *
 * Manages one gateway (4 GB per user) end to end: floating IP, persistent state
 * volume, the VM itself, and the Cloudflare A record that points at it. The DNS
 * record depends on the floating IP, so rebuilding the VM keeps DNS correct
 * automatically - that dependency is the reason this is Terraform rather than a
 * standalone script.
 *
 * Split by lifecycle:
 *   PERSISTENT  floating IP, state volume   - survive VM replacement
 *   DISPOSABLE  the instance                - safe to taint and recreate
 *
 * State (TLS cert, JupyterHub user database, user notebooks) lives on the
 * volume, NOT the root disk, so a rebuild does not lose accounts or work and no
 * private key is ever placed in terraform state or cloud-init user-data.
 *
 * Scope is one gateway. Workers hold no state and stay CLI-managed; see
 * ../OPENSTACK-CLI.md.
 */

terraform {
  required_version = ">= 1.5"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 2.1"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

provider "openstack" {
  cloud = var.os_cloud # reads ~/.config/openstack/clouds.yaml
}

provider "cloudflare" {
  api_token = var.cf_api_token # Zone:DNS:Edit, scoped to one zone
}

# --- look-ups (by name, so IDs are not hardcoded) ----------------------------

data "openstack_images_image_v2" "ubuntu" {
  name        = "Ubuntu-22.04"
  most_recent = true
}

data "openstack_compute_flavor_v2" "gateway" {
  name = var.gateway_flavor
}

data "openstack_networking_network_v2" "private" {
  name = var.private_network
}

data "cloudflare_zone" "main" {
  name = var.cf_zone
}

# --- persistent: floating IP -------------------------------------------------
# Imported, not created. Keeping the address stable is what lets the VM be
# replaced without touching DNS at Cloudflare.

resource "openstack_networking_floatingip_v2" "gw2" {
  pool = var.external_network

  lifecycle {
    prevent_destroy = true # losing this means a new IP and a DNS change
  }
}

# --- persistent: state volume ------------------------------------------------
# Mounted at /srv/state and bind-mounted over the paths that must survive:
#   ssl/cloudflare/  TLS origin cert + key   (never in tfstate or user-data)
#   jupyterhub/      user database, cookie secret
#   userhomes/       user notebooks

resource "openstack_blockstorage_volume_v3" "gw2_state" {
  name        = "jupyterhub-gateway2-state"
  size        = var.state_volume_gb
  description = "Persistent JupyterHub state: TLS, user DB, notebooks"

  lifecycle {
    prevent_destroy = true # this is the data that matters
  }
}

# --- disposable: the instance ------------------------------------------------

resource "openstack_compute_instance_v2" "gw2" {
  name            = "jupyterhub-gateway2"
  image_id        = data.openstack_images_image_v2.ubuntu.id
  flavor_id       = data.openstack_compute_flavor_v2.gateway.id
  key_pair        = var.keypair
  security_groups = ["gw-web", "dask-internal"]

  network {
    uuid = data.openstack_networking_network_v2.private.id
  }

  user_data = templatefile("${path.module}/cloud-init-gateway2.yaml.tftpl", {
    hostname          = "${var.gw2_subdomain}.${var.cf_zone}"
    admin_user        = var.admin_user
    mem_limit         = var.gw2_mem_limit
    concurrent_users  = var.gw2_concurrent_users
    scheduler_address = var.scheduler_address
    # Rendered as a Python list, wrapped in set() by the template.
    allowed_users_json = jsonencode(var.allowed_users)
    cull_timeout       = var.cull_timeout
  })

  # Changing user_data replaces the VM. That is intended - it is how a config
  # change is rolled out - and it is safe because state lives on the volume.
  lifecycle {
    ignore_changes = [image_id] # do not replace on a new Ubuntu image release
  }
}

resource "openstack_compute_volume_attach_v2" "gw2_state" {
  instance_id = openstack_compute_instance_v2.gw2.id
  volume_id   = openstack_blockstorage_volume_v3.gw2_state.id
  # OpenStack may ignore this hint (disks appear as sda/sdb here), so
  # cloud-init detects the non-root disk rather than trusting the name.
  device = "/dev/vdb"
}

# The instance's network[0].port attribute is empty at apply time, so using it
# directly associates the floating IP to nothing: the association "succeeds"
# but the IP stays DOWN and the host is unreachable. Look the port up instead,
# after the instance exists.
data "openstack_networking_port_v2" "gw2" {
  device_id  = openstack_compute_instance_v2.gw2.id
  network_id = data.openstack_networking_network_v2.private.id
}

resource "openstack_networking_floatingip_associate_v2" "gw2" {
  floating_ip = openstack_networking_floatingip_v2.gw2.address
  port_id     = data.openstack_networking_port_v2.gw2.id
}

# --- DNS ---------------------------------------------------------------------
# Proxied, so Cloudflare terminates TLS at the edge and the origin IP stays
# hidden. Requires SSL mode "Full (strict)" on the zone and the origin
# certificate installed on the volume.

resource "cloudflare_record" "gw2" {
  zone_id = data.cloudflare_zone.main.id
  name    = var.gw2_subdomain
  content = openstack_networking_floatingip_v2.gw2.address
  type    = "A"
  proxied = true
  comment = "EWC JupyterHub gateway 2 - managed by Terraform"
}

output "url" {
  value = "https://${var.gw2_subdomain}.${var.cf_zone}/"
}

output "floating_ip" {
  value = openstack_networking_floatingip_v2.gw2.address
}

output "private_ip" {
  value = openstack_compute_instance_v2.gw2.access_ip_v4
}
