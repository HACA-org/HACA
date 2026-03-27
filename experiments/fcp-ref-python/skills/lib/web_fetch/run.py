#!/usr/bin/env python3
"""web_fetch — fetch URL content; only allowlisted URL prefixes permitted."""

from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ALLOWED_SCHEMES = ("https://", "http://")
_DEFAULT_MAX_BYTES = 512 * 1024  # 512 KB


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    url = str(params.get("url", "")).strip()
    if not url:
        print(json.dumps({"error": "missing required param: url"}))
        sys.exit(1)

    # validate scheme
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        print(json.dumps({"error": f"URL scheme not permitted (only http/https): {url}"}))
        sys.exit(1)

    # load allowlist and max_bytes from manifest
    manifest_path = entity_root / "skills" / "lib" / "web_fetch" / "manifest.json"
    allowlist: list[str] = []
    max_bytes: int = _DEFAULT_MAX_BYTES
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowlist = [str(a) for a in manifest.get("allowlist", [])]
        max_bytes = int(manifest.get("max_bytes", _DEFAULT_MAX_BYTES))

    # Normalise: ensure URL has a trailing slash after the host when there is no path,
    # so that "https://example.com" and "https://example.com/" match the same prefix.
    try:
        from urllib.parse import urlparse as _up
        _p = _up(url)
        if _p.path == "":
            url = url + "/"
    except Exception:
        pass

    # operator "allow once" bypass via env var — normalise the stored value the same
    # way so that "https://example.com" and "https://example.com/" are treated as equal.
    allow_once_raw = os.environ.get("FCP_WEB_FETCH_ALLOW_ONCE", "")
    allow_once = allow_once_raw
    if allow_once_raw:
        try:
            from urllib.parse import urlparse as _up2
            _p2 = _up2(allow_once_raw)
            if _p2.path == "":
                allow_once = allow_once_raw + "/"
        except Exception:
            pass
    if not (allow_once and allow_once == url):
        # allowlist empty = block all (secure default)
        if not allowlist:
            print(json.dumps({"error": f"URL not in allowlist: {url}"}))
            sys.exit(0)
        if not any(url.startswith(prefix) for prefix in allowlist):
            print(json.dumps({"error": f"URL not in allowlist: {url}"}))
            sys.exit(0)

    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            content = resp.read(max_bytes).decode("utf-8", errors="replace")
        print(json.dumps({"status": "ok", "url": url, "content": content}))
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error": f"HTTP {exc.code}: {url}"}))
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"network error: {exc.reason}"}))
        sys.exit(1)


main()
