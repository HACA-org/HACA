"""CMI dispatch — internal handlers for cmi_send and cmi_req tools.

These are system tools operated by the CMI component directly,
not skills dispatched through exec_. Mirrors the MIL pattern.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from pathlib import Path

from ..store import Layout


def _sign(privkey: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True)
    return hmac.HMAC(bytes.fromhex(privkey), body.encode(), hashlib.sha256).hexdigest()


def _load_baseline(layout: Layout) -> dict | None:
    if not layout.baseline.exists():
        return None
    try:
        return json.loads(layout.baseline.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_credential(layout: Layout) -> tuple[str, str]:
    """Return (node_identity, privkey) or ('', '') if not found."""
    if not layout.cmi_credential.exists():
        return "", ""
    try:
        cred = json.loads(layout.cmi_credential.read_text(encoding="utf-8"))
        return cred.get("node_identity", ""), cred.get("privkey", "")
    except Exception:
        return "", ""


def _resolve_endpoint(layout: Layout, cmi_cfg: dict, channel_cfg: dict) -> tuple[str, str | None]:
    """Return (endpoint_url, error_or_None)."""
    local_endpoint = cmi_cfg.get("endpoint", "").rstrip("/")
    if not local_endpoint:
        return "", "cmi.endpoint not declared in baseline"

    channel_role = channel_cfg.get("role", "host")
    if channel_role == "host":
        return local_endpoint, None

    # Peer: route to host endpoint
    node_identity, _ = _load_credential(layout)
    trusted_peers = cmi_cfg.get("trusted_peers", [])
    for tp in trusted_peers:
        if tp.get("node_identity") != node_identity and tp.get("endpoint"):
            return tp["endpoint"].rstrip("/"), None
    return "", "host endpoint not found in trusted_peers"


def dispatch_send(layout: Layout, params: dict) -> dict:
    """Handle cmi_send tool call."""
    chan_id = str(params.get("chan_id", "")).strip()
    msg_type = str(params.get("type", "")).strip()
    content = str(params.get("content", "")).strip()
    to = str(params.get("to", "")).strip()

    if not chan_id:
        return {"error": "missing required param: chan_id"}
    if msg_type not in ("general", "peer", "bb"):
        return {"error": "type must be one of: general, peer, bb"}
    if not content:
        return {"error": "missing required param: content"}
    if msg_type == "peer" and not to:
        return {"error": "to is required when type is 'peer'"}

    baseline = _load_baseline(layout)
    if baseline is None:
        return {"error": "baseline.json not found"}

    cmi_cfg = baseline.get("cmi", {})
    channels: list[dict] = cmi_cfg.get("channels", [])
    channel_cfg = next((c for c in channels if c.get("id") == chan_id), None)
    if channel_cfg is None:
        return {"error": f"channel {chan_id!r} not found in baseline"}
    if channel_cfg.get("status", "unknown") != "active":
        return {"error": f"channel {chan_id!r} is not active (status: {channel_cfg.get('status', 'unknown')})"}

    endpoint, err = _resolve_endpoint(layout, cmi_cfg, channel_cfg)
    if err:
        return {"error": err}

    node_identity, privkey = _load_credential(layout)

    payload: dict = {
        "type": f"msg:{msg_type}",
        "chan_id": chan_id,
        "from": node_identity,
        "content": content,
    }
    if msg_type == "peer":
        payload["to"] = to
    if privkey:
        payload["sig"] = _sign(privkey, {k: v for k, v in payload.items()})

    path = "/contribute" if msg_type == "bb" else "/message"
    url = f"{endpoint}/channel/{chan_id}{path}"

    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return {"status": "sent", "chan_id": chan_id, "type": msg_type, "response": result}
    except urllib.error.URLError as exc:
        return {"error": f"channel endpoint unreachable: {exc.reason}"}
    except Exception as exc:
        return {"error": f"send failed: {exc}"}


def dispatch_req(layout: Layout, params: dict) -> dict:
    """Handle cmi_req tool call."""
    op = str(params.get("op", "")).strip()
    chan_id = str(params.get("chan_id", "")).strip()

    if op not in ("bb", "status"):
        return {"error": "op must be one of: bb, status"}
    if not chan_id:
        return {"error": "missing required param: chan_id"}

    baseline = _load_baseline(layout)
    if baseline is None:
        return {"error": "baseline.json not found"}

    cmi_cfg = baseline.get("cmi", {})
    channels: list[dict] = cmi_cfg.get("channels", [])
    channel_cfg = next((c for c in channels if c.get("id") == chan_id), None)
    if channel_cfg is None:
        return {"error": f"channel {chan_id!r} not found in baseline"}
    if channel_cfg.get("status", "unknown") == "closed":
        return {"error": f"channel {chan_id!r} is closed — no further access permitted"}

    endpoint, err = _resolve_endpoint(layout, cmi_cfg, channel_cfg)
    if err:
        return {"error": err}

    url = f"{endpoint}/channel/{chan_id}/{'bb' if op == 'bb' else 'status'}"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return {"op": op, "chan_id": chan_id, **result}
    except urllib.error.URLError as exc:
        return {"error": f"channel endpoint unreachable: {exc.reason}"}
    except Exception as exc:
        return {"error": f"request failed: {exc}"}
