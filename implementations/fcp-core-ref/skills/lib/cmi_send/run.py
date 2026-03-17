#!/usr/bin/env python3
"""cmi_send — send a message to an active CMI channel via the local endpoint."""

from __future__ import annotations
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _sign(privkey: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True)
    return hmac.HMAC(bytes.fromhex(privkey), body.encode(), hashlib.sha256).hexdigest()


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    chan_id = str(params.get("chan_id", "")).strip()
    msg_type = str(params.get("type", "")).strip()
    content = str(params.get("content", "")).strip()
    to = str(params.get("to", "")).strip()

    if not chan_id:
        print(json.dumps({"error": "missing required param: chan_id"}))
        sys.exit(1)
    if msg_type not in ("general", "peer", "bb"):
        print(json.dumps({"error": "type must be one of: general, peer, bb"}))
        sys.exit(1)
    if not content:
        print(json.dumps({"error": "missing required param: content"}))
        sys.exit(1)
    if msg_type == "peer" and not to:
        print(json.dumps({"error": "to is required when type is 'peer'"}))
        sys.exit(1)

    # Read baseline
    baseline_path = entity_root / "state" / "baseline.json"
    if not baseline_path.exists():
        print(json.dumps({"error": "baseline.json not found"}))
        sys.exit(1)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"error": f"baseline parse error: {exc}"}))
        sys.exit(1)

    cmi_cfg = baseline.get("cmi", {})
    local_endpoint = cmi_cfg.get("endpoint", "").rstrip("/")
    if not local_endpoint:
        print(json.dumps({"error": "cmi.endpoint not declared in baseline"}))
        sys.exit(1)

    # Verify channel is active
    channels: list[dict] = cmi_cfg.get("channels", [])
    channel_cfg = next((c for c in channels if c.get("id") == chan_id), None)
    if channel_cfg is None:
        print(json.dumps({"error": f"channel {chan_id!r} not found in baseline"}))
        sys.exit(1)
    status = channel_cfg.get("status", "unknown")
    if status != "active":
        print(json.dumps({"error": f"channel {chan_id!r} is not active (status: {status})"}))
        sys.exit(1)

    # Resolve target endpoint: host receives messages; peers forward to host
    # For role=host, send to own endpoint. For role=peer, send to host endpoint.
    channel_role = channel_cfg.get("role", "host")
    if channel_role == "host":
        endpoint = local_endpoint
    else:
        # Find host endpoint from trusted_peers (first peer that is not self)
        cred_path_tmp = entity_root / "state" / "cmi" / "credential.json"
        my_ni = ""
        if cred_path_tmp.exists():
            try:
                my_ni = json.loads(cred_path_tmp.read_text(encoding="utf-8")).get("node_identity", "")
            except Exception:
                pass
        trusted_peers = cmi_cfg.get("trusted_peers", [])
        host_endpoint = ""
        for tp in trusted_peers:
            if tp.get("node_identity") != my_ni and tp.get("endpoint"):
                host_endpoint = tp["endpoint"].rstrip("/")
                break
        if not host_endpoint:
            print(json.dumps({"error": "host endpoint not found in trusted_peers"}))
            sys.exit(1)
        endpoint = host_endpoint

    # Load CMI credential
    cred_path = entity_root / "state" / "cmi" / "credential.json"
    node_identity = ""
    privkey = ""
    if cred_path.exists():
        try:
            cred = json.loads(cred_path.read_text(encoding="utf-8"))
            node_identity = cred.get("node_identity", "")
            privkey = cred.get("privkey", "")
        except Exception:
            pass

    # Build payload
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

    # Route: bb → /contribute, general/peer → /message
    path = "/contribute" if msg_type == "bb" else "/message"
    url = f"{endpoint}/channel/{chan_id}{path}"

    try:
        body = json.dumps(payload).encode()
        http_req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(http_req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            print(json.dumps({"status": "sent", "chan_id": chan_id, "type": msg_type, "response": result}))
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"channel endpoint unreachable: {exc.reason}"}))
    except Exception as exc:
        print(json.dumps({"error": f"send failed: {exc}"}))


main()
