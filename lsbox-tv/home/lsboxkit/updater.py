"""One-press update of the home screen from the fork, with rollback.

Layout (all owned by tv, no sudo needed):
  ~/.local/share/lsbox-src/      sparse git clone of the fork (lsbox-tv/ only)
  ~/.local/share/lsbox-home/     the running app
  ~/.local/share/lsbox-home.prev the previous version (rollback target)
  ~/.local/share/lsbox-guard     runs before each start; after 2 failed
                                 starts of a new version it puts .prev back
"""
import os
import shutil

from .util import HOME, run

SHARE = os.path.join(HOME, ".local", "share")
SRC = os.path.join(SHARE, "lsbox-src")
LIVE = os.path.join(SHARE, "lsbox-home")
PREV = LIVE + ".prev"
NEW = LIVE + ".new"
PENDING = os.path.join(LIVE, ".pending")


def git(*args, timeout=60):
    return run(["git", "-C", SRC] + list(args), timeout=timeout)


def branch():
    """The branch to follow. Remembered in .lsbox-branch, because after the
    first update the copy sits on a detached HEAD."""
    mark = os.path.join(SRC, ".lsbox-branch")
    code, out = git("rev-parse", "--abbrev-ref", "HEAD")
    b = out.strip()
    if code == 0 and b not in ("", "HEAD"):
        if not os.path.exists(mark):
            with open(mark, "w") as f:
                f.write(b + "\n")
        return b
    return open(mark).read().strip() if os.path.exists(mark) else ""


def check():
    """-> dict(state=uptodate|available|error, current, latest, needs_install, message)"""
    if not os.path.isdir(os.path.join(SRC, ".git")):
        return {"state": "error", "message": "No update source. Run install.sh once more."}
    b = branch()
    code, out = git("fetch", "--depth", "1", "--filter=blob:none", "origin", b, timeout=90)
    if code != 0:
        return {"state": "error", "message": "Could not reach GitHub"}
    _, cur = git("rev-parse", "HEAD")
    _, new = git("rev-parse", "FETCH_HEAD")
    cur, new = cur.strip(), new.strip()
    if cur == new:
        return {"state": "uptodate", "current": cur[:7], "latest": new[:7], "message": "Up to date"}
    _, names = git("diff", "--name-only", cur, new, "--", "lsbox-tv")
    files = [n for n in names.split() if n]
    needs_install = any(not n.startswith("lsbox-tv/home/") and not n.startswith("lsbox-tv/tests/")
                        and n != "lsbox-tv/README.md" for n in files)
    _, subject = git("log", "-1", "--format=%s", new)
    return {"state": "available", "current": cur[:7], "latest": new[:7], "needs_install": needs_install,
            "message": subject.strip()[:90]}


def apply():
    """Moves FETCH_HEAD in, swaps the app folder. Caller then restarts."""
    code, _ = git("checkout", "--detach", "FETCH_HEAD")
    if code != 0:
        return False, "git checkout failed"
    home_src = os.path.join(SRC, "lsbox-tv", "home")
    if not os.path.isfile(os.path.join(home_src, "lsbox_home.py")):
        return False, "update is missing files"
    shutil.rmtree(NEW, ignore_errors=True)
    shutil.copytree(home_src, NEW, ignore=shutil.ignore_patterns("__pycache__"))
    # keep the user's edited copy of nothing: config lives in ~/.config
    shutil.rmtree(PREV, ignore_errors=True)
    os.replace(LIVE, PREV)
    os.replace(NEW, LIVE)
    with open(PENDING, "w") as f:
        f.write("0\n")
    return True, "updated"


def confirm_good():
    """Called once the new version has run fine for a while."""
    try:
        os.remove(PENDING)
    except OSError:
        pass


def rollback():
    if not os.path.isdir(PREV):
        return False
    bad = LIVE + ".bad"
    shutil.rmtree(bad, ignore_errors=True)
    os.replace(LIVE, bad)
    os.replace(PREV, LIVE)
    return True
