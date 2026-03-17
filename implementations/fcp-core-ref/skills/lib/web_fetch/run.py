#!/usr/bin/env python3
"""web_fetch — fetch URL content; only allowlisted URL prefixes permitted."""

from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    url = str(params.get("url", "")).strip()
    if not url:
        print(json.dumps({"error": "missing required param: url"}))
        sys.exit(1)

    # load allowlist from manifest
    manifest_path = entity_root / "skills" / "lib" / "web_fetch" / "manifest.json"
    allowlist: list[str] = []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowlist = [str(a) for a in manifest.get("allowlist", [])]

    if allowlist and not any(url.startswith(prefix) for prefix in allowlist):
        print(json.dumps({"error": f"URL not in allowlist: {url}"}))
        sys.exit(1)

    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        print(json.dumps({"status": "ok", "url": url, "content": content}))
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error": f"HTTP {exc.code}: {url}"}))
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"network error: {exc.reason}"}))
        sys.exit(1)


main()
