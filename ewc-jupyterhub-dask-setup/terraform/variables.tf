variable "os_cloud" {
  description = "Cloud entry in ~/.config/openstack/clouds.yaml"
  type        = string
  default     = "openstack"
}

variable "cf_api_token" {
  description = "Cloudflare API token, scoped to Zone:DNS:Edit on cf_zone only. Never the Global API Key."
  type        = string
  sensitive   = true
}

variable "cf_zone" {
  description = "Cloudflare zone (domain) name"
  type        = string
  default     = "example.org"
}

variable "gw2_subdomain" {
  description = "Subdomain for gateway 2. One level only - Cloudflare free Universal SSL does not cover a.b.domain."
  type        = string
  default     = "hub-b"
}

variable "gateway_flavor" {
  description = "Flavor for the gateway. 8cpu-32gbmem-80gbdisk is the largest available on this tenancy - there is no 64 GB flavor."
  type        = string
  default     = "8cpu-32gbmem-80gbdisk"
}

variable "private_network" {
  type    = string
  default = "<your-private-network>"
}

variable "external_network" {
  type    = string
  default = "external-internet"
}

variable "keypair" {
  type    = string
  default = "<your-keypair>"
}

variable "admin_user" {
  description = "JupyterHub admin username. Must be registered FIRST at /hub/signup to receive admin rights."
  type        = string
  default     = "admin-username"
}

variable "gw2_mem_limit" {
  description = "Per-user memory, enforced via cgroups by SystemdSpawner."
  type        = string
  default     = "4G"
}

variable "gw2_concurrent_users" {
  description = "Concurrent servers. mem_limit x this must leave headroom on a 32 GB VM: 7 x 4G = 28G is the practical maximum."
  type        = number
  default     = 7

  validation {
    condition     = var.gw2_concurrent_users >= 1 && var.gw2_concurrent_users <= 7
    error_message = "More than 7 concurrent 4 GB servers leaves too little for the OS on a 32 GB flavor."
  }
}

variable "scheduler_address" {
  description = "Dask scheduler, hosted on gateway 1. Gateway 2 runs no scheduler of its own."
  type        = string
  default     = "tcp://<scheduler-private-ip>:8786"
}

variable "state_volume_gb" {
  description = "Persistent volume for TLS cert, JupyterHub database and user notebooks."
  type        = number
  default     = 100
}

variable "allowed_users" {
  description = <<-EOT
    Usernames auto-authorised at signup. NativeAuthenticator approves these
    without admin action; anyone else lands in the /hub/authorize queue.
    Lower case, no spaces - must match exactly what the user types at signup.
  EOT
  type        = list(string)
  default     = ["admin-username"]
}

variable "cull_timeout" {
  description = <<-EOT
    Seconds of inactivity before the idle-culler stops a server. The culler
    tracks NOTEBOOK activity, not the Dask cluster: work submitted
    asynchronously leaves the kernel idle while workers are busy, so a short
    timeout kills the Dask client mid-run and cancels pending futures.
    88800 (~24h) reclaims slots overnight without doing that.
  EOT
  type        = number
  default     = 88800
}
