# Append to /srv/jupyterhub/jupyterhub_config.py
#
#   scp -i ~/.ssh/id_ed25519 idle-culler-snippet.py ubuntu@<gateway-floating-ip>:/tmp/
#   sudo sh -c 'cat /tmp/idle-culler-snippet.py >> /srv/jupyterhub/jupyterhub_config.py'
#   sudo systemctl restart jupyterhub
#
# JupyterHub 2+ requires explicit scopes via load_roles; the older
# "'admin': True" on a service no longer grants any permissions.

# --- idle culling ---
c.JupyterHub.services = [
    {
        'name': 'idle-culler',
        'command': [
            '/opt/mamba/envs/dask/bin/python', '-m', 'jupyterhub_idle_culler',
            '--timeout=3600',        # cull servers idle > 1 hour
            '--cull-every=300',
        ],
    },
]

c.JupyterHub.load_roles = [
    {
        'name': 'idle-culler',
        'services': ['idle-culler'],
        'scopes': [
            'list:users',
            'read:users:activity',
            'read:servers',
            'delete:servers',
        ],
    },
]
