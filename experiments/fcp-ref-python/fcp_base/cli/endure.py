"""
CLI endure subcommands — sync, origin, chain.

These commands manage the entity's git-based backup/restore workflow
and integrity chain display, outside of a session.
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

from .. import ui

if TYPE_CHECKING:
    from ..store import Layout


def run_endure_sync(layout: "Layout") -> None:
    """Sync entity root with its git remote."""
    root = str(layout.root)

    def _git(*args: str) -> tuple[int, str, str]:
        r = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def _git_out(*args: str) -> str:
        _, out, _ = _git(*args)
        return out

    code, _, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        ui.print_err("This entity root is not a git repository.")
        ui.print_err("Run 'git init' inside the entity root and add a remote to use sync.")
        return

    remotes = _git_out("remote")
    if "origin" not in remotes.splitlines():
        ui.print_err("No 'origin' remote configured.")
        ui.print_err("Add one with: git remote add origin <url>")
        return

    ui.print_info("Fetching from origin...")
    code, _, err = _git("fetch", "origin")
    if code != 0:
        ui.print_err(f"git fetch failed: {err}")
        return

    branch = _git_out("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        ui.print_err("Detached HEAD — cannot sync. Check out a branch first.")
        return

    remote_ref = f"origin/{branch}"
    remote_exists_code, _, _ = _git("rev-parse", "--verify", remote_ref)

    _, status_out, _ = _git("status", "--porcelain")
    has_local_changes = bool(status_out.strip())

    ui.hr("endure sync")

    if remote_exists_code != 0:
        ui.print_info(f"Branch '{branch}' has no upstream on origin yet.")
        ahead = int(_git_out("rev-list", "--count", "HEAD") or "0")
        behind = 0
    else:
        ahead_str = _git_out("rev-list", "--count", f"{remote_ref}..HEAD")
        behind_str = _git_out("rev-list", "--count", f"HEAD..{remote_ref}")
        ahead = int(ahead_str or "0")
        behind = int(behind_str or "0")

    if has_local_changes:
        ui.print_warn("Uncommitted local changes detected.")
    if remote_exists_code != 0:
        ui.print_info(f"Local branch '{branch}' not yet pushed to origin.")
    elif ahead == 0 and behind == 0:
        ui.print_ok("Entity is in sync with origin.")
    elif ahead > 0 and behind == 0:
        ui.print_info(f"Local is {ahead} commit(s) ahead of origin/{branch}.")
    elif ahead == 0 and behind > 0:
        ui.print_info(f"Local is {behind} commit(s) behind origin/{branch}.")
    else:
        ui.print_warn(f"Diverged: {ahead} local commit(s), {behind} remote commit(s).")

    print()

    actions: list[str] = []
    if has_local_changes:
        actions.append("commit local changes")
    if remote_exists_code != 0 or ahead > 0:
        actions.append(f"push to origin/{branch}")
    if behind > 0:
        actions.append(f"pull from origin/{branch} (fast-forward)")
    if ahead > 0 and behind > 0:
        actions.append(f"rebase local on origin/{branch}")
    actions.append("show git status")
    actions.append("show log (last 10)")
    actions.append("abort — do nothing")

    choice = ui.pick_one("Action", actions, default_idx=0)
    if choice is None or choice == "abort — do nothing":
        ui.print_info("Sync aborted.")
        return

    print()

    if choice == "commit local changes":
        msg = ui.ask("Commit message", "endure sync")
        if not msg:
            msg = f"endure sync {int(time.time())}"
        code, out, err = _git("add", "-A")
        if code != 0:
            ui.print_err(f"git add failed: {err}")
            return
        code, out, err = _git("commit", "-m", msg)
        if code != 0:
            ui.print_err(f"git commit failed: {err or out}")
        else:
            ui.print_ok(f"Committed: {out.splitlines()[0] if out else 'ok'}")

    elif choice.startswith("push to origin/"):
        code, out, err = _git("push", "origin", branch)
        if code != 0:
            ui.print_err(f"git push failed: {err}")
        else:
            ui.print_ok(f"Pushed to origin/{branch}.")

    elif choice.startswith("pull from origin/"):
        code, out, err = _git("pull", "--ff-only", "origin", branch)
        if code != 0:
            ui.print_err(f"git pull failed: {err}")
            ui.print_info("Tip: use 'rebase local on origin' if fast-forward is not possible.")
        else:
            ui.print_ok(f"Pulled: {out.splitlines()[0] if out else 'ok'}")

    elif choice.startswith("rebase local on origin/"):
        code, out, err = _git("rebase", f"origin/{branch}")
        if code != 0:
            ui.print_err(f"git rebase failed: {err}")
            ui.print_err("Resolve conflicts manually, then run 'git rebase --continue'.")
        else:
            ui.print_ok("Rebase complete.")

    elif choice == "show git status":
        code, out, _ = _git("status")
        print(out)

    elif choice == "show log (last 10)":
        code, out, _ = _git("log", "--oneline", "-10")
        print(out)

    print()


def run_endure_origin(layout: "Layout") -> None:
    """Set or update the 'origin' git remote for this entity root."""
    root = str(layout.root)

    def _git(*args: str) -> tuple[int, str, str]:
        r = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    code, _, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        ui.print_err("This entity root is not a git repository.")
        ui.print_err("Run 'git init' inside the entity root first.")
        return

    ui.hr("endure origin")

    code, current_url, _ = _git("remote", "get-url", "origin")
    if code == 0:
        ui.print_info(f"Current origin: {current_url}")
    else:
        ui.print_info("No origin remote configured yet.")

    print()
    new_url = ui.ask("Remote URL (leave blank to cancel)", "")
    if not new_url:
        ui.print_info("Cancelled.")
        return

    if code == 0:
        set_code, _, err = _git("remote", "set-url", "origin", new_url)
        if set_code != 0:
            ui.print_err(f"Failed to update origin: {err}")
        else:
            ui.print_ok(f"origin updated → {new_url}")
    else:
        add_code, _, err = _git("remote", "add", "origin", new_url)
        if add_code != 0:
            ui.print_err(f"Failed to add origin: {err}")
        else:
            ui.print_ok(f"origin added → {new_url}")

    print()


def run_endure_chain(layout: "Layout") -> None:
    """Display the integrity chain entries."""
    from ..operator import print_integrity_chain
    print_integrity_chain(layout)
