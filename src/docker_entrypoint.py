"""Docker entrypoint for Qzone3TG.

The image runs as the unprivileged ``qzone`` user by default. Starting the
container as root (for example with ``--user root``) is still supported: the
entrypoint repairs the ownership of the writable mount points, warns about it,
and then drops the privileges again. Privileges are always dropped: if the
repair fails, the entrypoint warns and still runs the app as the unprivileged
user. Starting as any other user changes nothing; fixing mount permissions is
then up to the operator.
"""

from __future__ import annotations

import os
import pwd
import sys

APP_USER = "qzone"
APP_PYZ = "/app/app.pyz"
WRITABLE = ("/app/log", "/app/data")


def note(message: str) -> None:
    print(f"[qzone3tg] {message}", file=sys.stderr, flush=True)


def chown_tree(path: str, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)
    for root, dirs, files in os.walk(path):
        for name in (*dirs, *files):
            os.chown(os.path.join(root, name), uid, gid, follow_symlinks=False)


def fix_mounts(uid: int, gid: int) -> bool:
    """Give the app user ownership of its writable mount points."""
    ok = True
    for path in WRITABLE:
        try:
            os.makedirs(path, exist_ok=True)
            chown_tree(path, uid, gid)
        except OSError as e:
            note(f"WARNING: cannot fix ownership of {path}: {e}")
            ok = False
    return ok


def warn_if_unwritable(uid: int) -> None:
    for path in WRITABLE:
        if os.path.isdir(path) and not os.access(path, os.W_OK | os.X_OK):
            note(
                f"WARNING: {path} is not writable by uid {uid}. Fix the ownership "
                "of the host directory mounted there, or start with --user root "
                "to let the entrypoint fix it automatically."
            )


def exec_app() -> None:
    os.execv(sys.executable, [sys.executable, APP_PYZ, *sys.argv[1:]])


def main() -> None:
    uid = os.geteuid()

    if uid != 0:
        warn_if_unwritable(uid)
        exec_app()

    note(
        "WARNING: started as root; fixing ownership of writable mounts and "
        f"dropping privileges to '{APP_USER}'. Host-visible mounts will be "
        f"chowned. Start with --user {APP_USER} to skip this step."
    )

    try:
        user = pwd.getpwnam(APP_USER)
    except KeyError:
        note(f"ERROR: user '{APP_USER}' is missing from the image")
        raise SystemExit(1)

    if not fix_mounts(user.pw_uid, user.pw_gid):
        note(
            "WARNING: could not repair every writable mount; refusing to run "
            f"as root, continuing as '{APP_USER}'. Fix the mount permissions "
            "if the app fails to start."
        )

    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    exec_app()


if __name__ == "__main__":
    main()
