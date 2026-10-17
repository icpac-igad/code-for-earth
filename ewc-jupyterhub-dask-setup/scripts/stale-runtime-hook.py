# Append to /srv/jupyterhub/jupyterhub_config.py
#
#   scp stale-runtime-hook.py ubuntu@<gateway-ip>:/tmp/
#   sudo sh -c 'cat /tmp/stale-runtime-hook.py >> /srv/jupyterhub/jupyterhub_config.py'
#   sudo systemctl restart jupyterhub
#
# Fixes: 500 Internal Server Error, "Unhandled error starting server <user>",
#        FileExistsError: [Errno 17] File exists: '/run/jupyter-<user>'
#
# Cause: with SystemdSpawner.dynamic_users, systemd creates /run/jupyter-<user>
# as a symlink into /run/private/. When the unit stops - on logout, on an
# idle-culler cull, or on a Hub restart - the target is removed but the symlink
# can be left behind. SystemdSpawner then calls
# os.makedirs(path, exist_ok=True), which still raises FileExistsError when the
# path exists but is not a directory. Every subsequent spawn for that user
# fails until the stale entry is cleared.
#
# A systemd-tmpfiles rule also works, but systemd-tmpfiles-clean.timer runs
# daily by default - a user culled at 10:00 would still fail at 11:00. This
# hook runs immediately before each spawn instead.

def _clear_stale_runtime_dir(spawner):
    """Remove a dangling /run/jupyter-<user> left by a previous unit."""
    import os
    import shutil

    path = f"/run/jupyter-{spawner.user.name}"
    try:
        if os.path.islink(path) and not os.path.exists(path):
            # Dangling symlink: target already cleaned up by systemd.
            os.unlink(path)
            spawner.log.info("cleared stale runtime symlink %s", path)
        elif os.path.isdir(path) and not os.listdir(path):
            # Empty leftover directory - safe to remove.
            shutil.rmtree(path, ignore_errors=True)
            spawner.log.info("cleared stale runtime dir %s", path)
    except OSError as e:
        # Never block a spawn because cleanup failed; the spawn itself will
        # report a clearer error if the path is genuinely in the way.
        spawner.log.warning("could not clear %s: %s", path, e)


c.Spawner.pre_spawn_hook = _clear_stale_runtime_dir
