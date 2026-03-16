#!/usr/bin/env python3
"""cmi_req — read state from an active CMI channel via the local endpoint."""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    op = str(params.get("op", "")).strip()
    chan_id = str(params.get("chan_id", "")).strip()

    if op not in ("bb", "status"):
        print(json.dumps({"error": "op must be one of: bb, status"}))
        sys.exit(1)
    if not chan_id:
        print(json.dumps({"error": "missing required param: chan_id"}))
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

    # Verify channel exists and is not closed
    channels: list[dict] = cmi_cfg.get("channels", [])
    channel_cfg = next((c for c in channels if c.get("id") == chan_id), None)
    if channel_cfg is None:
        print(json.dumps({"error": f"channel {chan_id!r} not found in baseline"}))
        sys.exit(1)
    status = channel_cfg.get("status", "unknown")
    if status == "closed":
        print(json.dumps({"error": f"channel {chan_id!r} is closed — no further access permitted"}))
        sys.exit(1)

    # Resolve endpoint: host uses local; peer routes to host
    channel_role = channel_cfg.get("role", "host")
    if channel_role == "host":
        endpoint = local_endpoint
    else:
        cred_path = entity_root / "state" / "cmi" / "credential.json"
        my_ni = ""
        if cred_path.exists():
            try:
                my_ni = json.loads(cred_path.read_text(encoding="utf-8")).get("node_identity", "")
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

    # Build URL
    if op == "bb":
        url = f"{endpoint}/channel/{chan_id}/bb"
    else:  # status
        url = f"{endpoint}/channel/{chan_id}/status"

    try:
        http_req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(http_req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            print(json.dumps({"op": op, "chan_id": chan_id, **result}))
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"channel endpoint unreachable: {exc.reason}"}))
    except Exception as exc:
        print(json.dumps({"error": f"request failed: {exc}"}))


main()
