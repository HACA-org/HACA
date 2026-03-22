"""
SIL Passive Distress Beacon and Session Token — §10.7 / §5.3.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ..formats import SessionToken
from ..store import atomic_write, read_json
from .utils import utcnow

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# §10.7 Passive Distress Beacon
# ---------------------------------------------------------------------------

def activate_beacon(layout: "Layout", cause: str, consecutive_failures: int) -> None:
    """Write state/distress.beacon atomically."""
    atomic_write(
        layout.distress_beacon,
        {
            "cause": cause,
            "ts": utcnow(),
            "consecutive_failures": consecutive_failures,
        },
    )
    from ..hooks import run_hook
    run_hook(layout, "on_beacon_activated", {
        "cause": cause,
        "consecutive_failures": consecutive_failures,
    })


def beacon_is_active(layout: "Layout") -> bool:
    return layout.distress_beacon.exists()


def clear_beacon(layout: "Layout") -> None:
    """Remove state/distress.beacon.  Only called after Operator + SIL confirm."""
    if layout.distress_beacon.exists():
        layout.distress_beacon.unlink()


# ---------------------------------------------------------------------------
# §5.3 Session Token
# ---------------------------------------------------------------------------

def issue_session_token(layout: "Layout") -> str:
    """Write state/sentinels/session.token and return the new session_id."""
    from ..cmi.identity import read_genesis_omega
    try:
        genesis_omega = read_genesis_omega(layout)
    except RuntimeError:
        genesis_omega = ""
    session_id = str(uuid.uuid4())
    token = SessionToken(
        session_id=session_id,
        issued_at=utcnow(),
        genesis_omega=genesis_omega,
        revoked_at=None,
    )
    layout.sentinels_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(layout.session_token, token.to_dict())
    return session_id


def revoke_session_token(layout: "Layout") -> None:
    """Stamp revoked_at on the session token atomically."""
    if not layout.session_token.exists():
        return
    d = read_json(layout.session_token)
    d["revoked_at"] = utcnow()
    atomic_write(layout.session_token, d)


def session_token_present(layout: "Layout") -> bool:
    return layout.session_token.exists()


def read_session_token(layout: "Layout") -> SessionToken | None:
    if not layout.session_token.exists():
        return None
    return SessionToken.from_dict(read_json(layout.session_token))
