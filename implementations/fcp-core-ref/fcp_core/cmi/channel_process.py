"""
CMI Channel Process — FCP-Core CMI §3, §4, §7.

Launched by the FCP as a subprocess for each open Mesh Channel.
One process per channel, ephemeral — exits when the channel closes.

Usage (internal, called by cli.py):
    python3 -m fcp_core.cmi.channel_process <entity_root> <chan_id> <role>

    role: host | peer | observer

Architecture:
    Every participating entity runs a small HTTP server on the port declared
    in baseline.cmi.endpoint (e.g. http://localhost:7700).  The chan_id is
    embedded in every request path so a single port can serve one channel at
    a time (HACA-Core constraint: private channels only, rarely concurrent).

    Message types:
        msg:general  — ephemeral broadcast to all participants, no declared recipient
        msg:peer     — ephemeral broadcast to all participants, addressed to one peer
                       (all can see, only the addressed peer is expected to respond)
        msg:bb       — durable Blackboard contribution, sequenced by Host, broadcast to all

    Host endpoints (served by this process when role=host):
        GET  /ping                     — liveness check
        POST /channel/<id>/ready       — peer announces readiness; host issues Enrollment Token
        POST /channel/<id>/enroll      — peer enrollment request (requires Enrollment Token)
        POST /channel/<id>/message     — peer sends msg:general or msg:peer
        POST /channel/<id>/contribute  — peer submits msg:bb (Blackboard contribution)
        POST /channel/<id>/close       — operator signals close
        GET  /channel/<id>/bb          — download current Blackboard

    Peer/Observer endpoints (served when role=peer|observer):
        GET  /ping                     — liveness check
        POST /channel/<id>/stimulus    — Host delivers any stimulus type

    When the Host receives a message (msg:general / msg:peer) it:
        1. Validates sender identity (node_identity in trusted_peers + signature)
        2. Broadcasts to all enrolled peers via POST /stimulus
        3. Writes CMI_MSG_GENERAL or CMI_MSG_PEER to entity's io/inbox/

    When the Host receives a contribution (msg:bb) it:
        1. Validates sender identity + signature
        2. Assigns next sequence number
        3. Appends to blackboard.jsonl
        4. Broadcasts the sequenced entry to all enrolled peers via POST /stimulus
        5. Writes CMI_MSG_BB to entity's io/inbox/ as a CPE stimulus

    When a Peer/Observer receives a stimulus it:
        1. Validates sender (Host node_identity + signature)
        2. Writes CMI_MSG_GENERAL, CMI_MSG_PEER, CMI_MSG_BB, or CMI_CONTROL to io/inbox/

Signing:
    Every request body includes a "sig" field: HMAC-SHA256 over the
    JSON-serialised payload (excluding the "sig" field itself), using the
    sender's privkey. Recipients verify using the sender's pubkey from
    trusted_peers (or credential for Host→Peer).

Integrity faults are logged to integrity.log with MIF-* codes.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen, Request


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> None:
    """Entry point: argv = [entity_root, chan_id, role]"""
    if len(argv) < 3:
        print("usage: channel_process <entity_root> <chan_id> <role>", file=sys.stderr)
        sys.exit(1)

    entity_root = Path(argv[0]).resolve()
    chan_id = argv[1]
    role = argv[2].lower()

    if role not in ("host", "peer", "observer"):
        print(f"invalid role: {role}", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, str(entity_root))
    from fcp_core.store import Layout
    layout = Layout(entity_root)

    process = ChannelProcess(layout, chan_id, role)
    process.run()


# ---------------------------------------------------------------------------
# Channel Process
# ---------------------------------------------------------------------------

class ChannelProcess:
    """Manages one side of a Mesh Channel — Host, Peer, or Observer."""

    def __init__(self, layout: "Any", chan_id: str, role: str) -> None:
        self.layout = layout
        self.chan_id = chan_id
        self.role = role
        self._closing = threading.Event()
        self._bb_seq = 0
        self._enrolled_peers: list[dict[str, Any]] = []  # [{node_identity, endpoint, pubkey, role}]
        self._enrollment_tokens: dict[str, dict[str, Any]] = {}  # token → {node_identity, role, expiry, used}
        self._close_token: str = ""
        self._lock = threading.Lock()

        # Load config
        self._baseline = self._load_baseline()
        self._cmi_cfg = self._baseline.get("cmi", {})
        self._credential = self._load_credential()
        self._channel_cfg = self._find_channel_cfg()

        # Ensure channel dirs exist
        self.layout.cmi_channel_dir(chan_id).mkdir(parents=True, exist_ok=True)

        # Restore enrolled peers and BB seq from disk (host crash/restart recovery)
        if self.role == "host":
            p_path = self.layout.cmi_participants(chan_id)
            if p_path.exists():
                try:
                    from ..store import read_json
                    saved = read_json(p_path)
                    self._enrolled_peers = saved.get("peers", [])
                except Exception:
                    pass
            bb_path = self.layout.cmi_blackboard(chan_id)
            if bb_path.exists():
                try:
                    lines = [l for l in bb_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                    if lines:
                        import json as _json
                        last = _json.loads(lines[-1])
                        self._bb_seq = int(last.get("seq", 0))
                except Exception:
                    pass

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    def run(self) -> None:
        import secrets as _secrets
        endpoint = self._cmi_cfg.get("endpoint", "http://localhost:7700")
        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 7700

        # Generate a single-use close token — stored in Entity Store so only
        # the local Operator (with filesystem access) can issue a close signal.
        self._close_token = _secrets.token_hex(32)
        from ..store import atomic_write
        atomic_write(self.layout.cmi_close_token(self.chan_id), {"token": self._close_token})

        handler_factory = self._make_handler()
        server = HTTPServer((host, port), handler_factory)

        _log(f"[CMI] {self.role} process started: chan={self.chan_id} endpoint={endpoint}")
        self._update_participants_status("active")

        if self.role == "peer":
            threading.Thread(target=self._announce_ready, daemon=True).start()

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            self._closing.wait()
        except KeyboardInterrupt:
            pass
        finally:
            _log(f"[CMI] closing channel: {self.chan_id}")
            server.shutdown()
            self._update_participants_status("closed")
            self._update_channel_status("closed")
            # Remove close token on clean shutdown
            try:
                self.layout.cmi_close_token(self.chan_id).unlink(missing_ok=True)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # HTTP handler factory
    # -----------------------------------------------------------------------

    def _make_handler(self):
        process = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # suppress default access log

            def do_GET(self):
                if self.path == "/ping":
                    self._ok({"status": "ok", "ts": int(time.time())})
                elif self.path == f"/channel/{process.chan_id}/bb":
                    process._handle_bb_get(self)
                else:
                    self._not_found()

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    payload = json.loads(body)
                except Exception:
                    self._bad_request("invalid JSON")
                    return

                if self.path == f"/channel/{process.chan_id}/ready":
                    process._handle_ready(self, payload)
                elif self.path == f"/channel/{process.chan_id}/enroll":
                    process._handle_enroll(self, payload)
                elif self.path == f"/channel/{process.chan_id}/message":
                    process._handle_message(self, payload)
                elif self.path == f"/channel/{process.chan_id}/contribute":
                    process._handle_contribute(self, payload)
                elif self.path == f"/channel/{process.chan_id}/stimulus":
                    process._handle_stimulus(self, payload)
                elif self.path == f"/channel/{process.chan_id}/close":
                    process._handle_close(self, payload)
                else:
                    self._not_found()

            def _ok(self, data: dict) -> None:
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _bad_request(self, msg: str) -> None:
                body = json.dumps({"error": msg}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _not_found(self) -> None:
                self.send_response(404)
                self.end_headers()

            def _forbidden(self, msg: str) -> None:
                body = json.dumps({"error": msg}).encode()
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return _Handler

    # -----------------------------------------------------------------------
    # Host: enrollment
    # -----------------------------------------------------------------------

    def _handle_enroll(self, handler, payload: dict) -> None:
        """Host receives an enrollment request from a peer."""
        if self.role != "host":
            handler._forbidden("not host")
            return

        node_identity = payload.get("node_identity", "")
        sig = payload.get("sig", "")
        endpoint = payload.get("endpoint", "")
        token = payload.get("enrollment_token", "")

        # Validate against trusted_peers
        peer_cfg = self._find_trusted_peer(node_identity)
        if peer_cfg is None:
            self._log_mif("MIF-ENROLL", f"enrollment from unknown node: {node_identity[:20]}")
            handler._forbidden("not in trusted peers")
            return

        # Verify signature over payload minus "sig"
        check = {k: v for k, v in payload.items() if k != "sig"}
        if not self._verify(peer_cfg.get("pubkey", ""), check, sig):
            self._log_mif("MIF-AUTH", f"enrollment auth failure: {node_identity[:20]}")
            handler._forbidden("authentication failure")
            return

        # Validate Enrollment Token (private channels require a token)
        with self._lock:
            token_data = self._enrollment_tokens.get(token)
        if token_data is None:
            self._log_mif("MIF-ENROLL", f"missing or invalid enrollment token: {node_identity[:20]}")
            handler._forbidden("invalid enrollment token")
            return
        if token_data.get("used"):
            self._log_mif("MIF-ENROLL", f"enrollment token already used: {node_identity[:20]}")
            handler._forbidden("enrollment token already used")
            return
        if int(time.time()) > token_data.get("expiry", 0):
            self._log_mif("MIF-ENROLL", f"enrollment token expired: {node_identity[:20]}")
            handler._forbidden("enrollment token expired")
            return
        if token_data.get("node_identity") != node_identity:
            self._log_mif("MIF-AUTH", f"enrollment token node_identity mismatch: {node_identity[:20]}")
            handler._forbidden("enrollment token mismatch")
            return

        # Mark token as used (single-use)
        with self._lock:
            self._enrollment_tokens[token]["used"] = True

        assigned_role = token_data.get("role", "peer")

        with self._lock:
            # Replace existing entry if reconnecting
            self._enrolled_peers = [p for p in self._enrolled_peers if p["node_identity"] != node_identity]
            self._enrolled_peers.append({
                "node_identity": node_identity,
                "endpoint": endpoint,
                "pubkey": peer_cfg.get("pubkey", ""),
                "role": assigned_role,
            })
            self._save_participants()

        # Send current BB state as response (late-joiner support)
        bb_entries = self._read_bb()
        handler._ok({"enrolled": True, "role": assigned_role, "blackboard": bb_entries})
        _log(f"[CMI] enrolled peer: {node_identity[:20]}... on {self.chan_id}")
        self._write_inbox_stimulus("CMI_CONTROL", {
            "event": "peer_enrolled",
            "node_identity": node_identity,
            "chan_id": self.chan_id,
        })

    def _handle_ready(self, handler, payload: dict) -> None:
        """Host receives a ready announcement from a peer — issues an Enrollment Token."""
        import secrets
        if self.role != "host":
            handler._forbidden("not host")
            return

        node_identity = payload.get("node_identity", "")
        sig = payload.get("sig", "")

        peer_cfg = self._find_trusted_peer(node_identity)
        if peer_cfg is None:
            self._log_mif("MIF-ENROLL", f"ready from unknown node: {node_identity[:20]}")
            handler._forbidden("not in trusted peers")
            return

        check = {k: v for k, v in payload.items() if k != "sig"}
        if not self._verify(peer_cfg.get("pubkey", ""), check, sig):
            self._log_mif("MIF-AUTH", f"ready auth failure: {node_identity[:20]}")
            handler._forbidden("authentication failure")
            return

        # Reject ready/enroll if channel is no longer accepting participants
        ch_status = self._channel_cfg.get("status", "created")
        if ch_status in ("closing", "closed"):
            handler._forbidden(f"channel is {ch_status}")
            return

        declared = self._channel_cfg.get("participants", [])
        if node_identity not in declared:
            self._log_mif("MIF-ENROLL", f"node not in channel participant list: {node_identity[:20]}")
            handler._forbidden("not in channel participant list")
            return

        # Issue single-use Enrollment Token (TTL: 5 minutes)
        token = secrets.token_hex(32)
        with self._lock:
            self._enrollment_tokens[token] = {
                "node_identity": node_identity,
                "role": "peer",
                "expiry": int(time.time()) + 300,
                "used": False,
            }

        handler._ok({
            "enrollment_token": token,
            "chan_id": self.chan_id,
            "task": self._channel_cfg.get("task", ""),
            "host_endpoint": self._cmi_cfg.get("endpoint", ""),
            "role": "peer",
        })
        _log(f"[CMI] enrollment token issued to: {node_identity[:20]}...")

    def _announce_ready(self) -> None:
        """Peer announces readiness to host — retries until host is reachable."""
        if self._credential is None:
            return
        my_ni = self._credential.get("node_identity", "")
        my_endpoint = self._cmi_cfg.get("endpoint", "")

        # Find host endpoint from trusted_peers (first FULL peer that is the host)
        participants = self._channel_cfg.get("participants", [])
        host_endpoint = ""
        for ni in participants:
            if ni == my_ni:
                continue
            peer_cfg = self._find_trusted_peer(ni)
            if peer_cfg:
                host_endpoint = peer_cfg.get("endpoint", "")
                break

        if not host_endpoint:
            _log("[CMI] peer: no host endpoint found — cannot announce ready")
            return

        payload = {
            "type": "CMI_READY",
            "chan_id": self.chan_id,
            "node_identity": my_ni,
            "endpoint": my_endpoint,
            "from": my_ni,
        }

        for attempt in range(1, 11):
            if self._closing.is_set():
                return
            signed = dict(payload)
            from .identity import sign_message
            privkey = self._credential.get("privkey", "")
            data = json.dumps(signed, sort_keys=True).encode()
            signed["sig"] = sign_message(privkey, data)

            try:
                body = json.dumps(signed).encode()
                req = Request(
                    host_endpoint + f"/channel/{self.chan_id}/ready",
                    data=body, headers={"Content-Type": "application/json"}, method="POST",
                )
                with urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read().decode())
                token = result.get("enrollment_token", "")
                if token:
                    _log(f"[CMI] peer: received enrollment token — enrolling...")
                    self._enroll_with_token(host_endpoint, token)
                    return
            except Exception as exc:
                _log(f"[CMI] peer: ready attempt {attempt}/10 failed: {exc}")
                time.sleep(2)

        _log("[CMI] peer: exhausted ready attempts — enrollment failed")

    def _enroll_with_token(self, host_endpoint: str, token: str) -> None:
        """Peer uses an Enrollment Token to enroll with the host."""
        if self._credential is None:
            return
        my_ni = self._credential.get("node_identity", "")
        my_endpoint = self._cmi_cfg.get("endpoint", "")
        privkey = self._credential.get("privkey", "")

        payload = {
            "type": "CMI_ENROLL",
            "chan_id": self.chan_id,
            "node_identity": my_ni,
            "endpoint": my_endpoint,
            "enrollment_token": token,
            "from": my_ni,
        }
        from .identity import sign_message
        data = json.dumps(payload, sort_keys=True).encode()
        payload["sig"] = sign_message(privkey, data)

        try:
            body = json.dumps(payload).encode()
            req = Request(
                host_endpoint + f"/channel/{self.chan_id}/enroll",
                data=body, headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            if result.get("enrolled"):
                _log(f"[CMI] peer: enrolled on {self.chan_id} role:{result.get('role')}")
                self._update_participants_status("active")
                # Write CMI_INVITE stimulus to CPE inbox with task context
                self._write_inbox_stimulus("CMI_CONTROL", {
                    "event": "enrolled",
                    "chan_id": self.chan_id,
                    "role": result.get("role", "peer"),
                    "task": self._channel_cfg.get("task", ""),
                    "blackboard": result.get("blackboard", []),
                })
            else:
                _log(f"[CMI] peer: enrollment rejected: {result}")
        except Exception as exc:
            _log(f"[CMI] peer: enrollment failed: {exc}")

    # -----------------------------------------------------------------------
    # Host: ephemeral messages (msg:general, msg:peer)
    # -----------------------------------------------------------------------

    def _handle_message(self, handler, payload: dict) -> None:
        """Host receives an ephemeral message from a peer — msg:general or msg:peer.

        Broadcasts to all enrolled peers. Not persisted to Blackboard.
        msg:peer includes a 'to' field (node_identity of addressee) for explicit
        addressing, but is still broadcast to all participants.
        """
        if self.role != "host":
            handler._forbidden("not host")
            return

        node_identity = payload.get("from", "")
        sig = payload.get("sig", "")
        msg_type = payload.get("type", "msg:general")
        content = payload.get("content", "")
        to = payload.get("to", "")  # only for msg:peer

        if msg_type not in ("msg:general", "msg:peer"):
            handler._bad_request("type must be msg:general or msg:peer")
            return

        if msg_type == "msg:peer" and not to:
            handler._bad_request("msg:peer requires 'to' field")
            return

        peer = self._resolve_sender(node_identity)
        if peer is None:
            self._log_mif("MIF-ROLE", f"message from non-enrolled node: {node_identity[:20]}")
            handler._forbidden("not enrolled")
            return

        pubkey = peer.get("pubkey", "")
        if pubkey:  # skip sig check for self-sent (host, pubkey="")
            check = {k: v for k, v in payload.items() if k != "sig"}
            if not self._verify(pubkey, check, sig):
                self._log_mif("MIF-AUTH", f"message auth failure: {node_identity[:20]}")
                handler._forbidden("authentication failure")
                return

        handler._ok({"received": True})

        # Broadcast to all enrolled peers (including sender — they see their own msg)
        broadcast = {
            "type": msg_type,
            "chan_id": self.chan_id,
            "from": node_identity,
            "content": content,
            "ts": int(time.time()),
        }
        if to:
            broadcast["to"] = to
        self._broadcast_to_peers(broadcast)

        # Write to local io/inbox/ as CPE stimulus
        inbox_type = "CMI_MSG_GENERAL" if msg_type == "msg:general" else "CMI_MSG_PEER"
        self._write_inbox_stimulus(inbox_type, broadcast)
        _log(f"[CMI] {msg_type} from {node_identity[:20]}..." + (f" to {to[:20]}..." if to else ""))

    # -----------------------------------------------------------------------
    # Host: contributions and broadcast
    # -----------------------------------------------------------------------

    def _handle_contribute(self, handler, payload: dict) -> None:
        """Host receives a BB contribution from a peer (msg:bb)."""
        if self.role != "host":
            handler._forbidden("not host")
            return

        node_identity = payload.get("from", "")
        sig = payload.get("sig", "")
        content = payload.get("content", "")

        peer = self._resolve_sender(node_identity)
        if peer is None:
            self._log_mif("MIF-ROLE", f"contribution from non-enrolled node: {node_identity[:20]}")
            handler._forbidden("not enrolled")
            return

        if peer.get("role") not in ("peer", "host"):
            self._log_mif("MIF-ROLE", f"observer tried to contribute: {node_identity[:20]}")
            handler._forbidden("observers cannot contribute")
            return

        pubkey = peer.get("pubkey", "")
        if pubkey:  # skip sig check for self-sent (host, pubkey="")
            check = {k: v for k, v in payload.items() if k != "sig"}
            if not self._verify(pubkey, check, sig):
                self._log_mif("MIF-AUTH", f"contribution auth failure: {node_identity[:20]}")
                handler._forbidden("authentication failure")
                return

        with self._lock:
            self._bb_seq += 1
            seq = self._bb_seq

        entry = {
            "seq": seq,
            "from": node_identity,
            "content": content,
            "ts": int(time.time()),
        }
        self._append_bb(entry)
        handler._ok({"seq": seq})

        # Broadcast to all enrolled peers
        broadcast = dict(entry)
        broadcast["chan_id"] = self.chan_id
        broadcast["type"] = "msg:bb"
        self._broadcast_to_peers(broadcast, exclude=node_identity)

        # Write to local io/inbox/ as CPE stimulus
        self._write_inbox_stimulus("CMI_MSG_BB", broadcast)
        _log(f"[CMI] msg:bb seq={seq} from {node_identity[:20]}...")

    # -----------------------------------------------------------------------
    # Peer/Observer: stimulus reception
    # -----------------------------------------------------------------------

    def _handle_stimulus(self, handler, payload: dict) -> None:
        """Peer/Observer receives a stimulus from the Host."""
        node_identity = payload.get("from", payload.get("host_identity", ""))
        sig = payload.get("sig", "")
        msg_type = payload.get("type", "CMI_MSG_GENERAL")

        # Validate sender is the Host or a trusted peer
        if node_identity:
            peer_cfg = self._find_trusted_peer(node_identity)
            pubkey = peer_cfg.get("pubkey", "") if peer_cfg else ""
            if pubkey:
                check = {k: v for k, v in payload.items() if k != "sig"}
                if not sig or not self._verify(pubkey, check, sig):
                    self._log_mif("MIF-AUTH", f"stimulus auth failure from {node_identity[:20]}")
                    handler._ok({"received": False, "error": "auth failure"})
                    return

        # Map wire type to inbox envelope type
        _type_map = {
            "msg:general": "CMI_MSG_GENERAL",
            "msg:peer":    "CMI_MSG_PEER",
            "msg:bb":      "CMI_MSG_BB",
        }
        inbox_type = _type_map.get(msg_type, msg_type)

        # Write to io/inbox/ as CPE stimulus
        self._write_inbox_stimulus(inbox_type, payload)
        handler._ok({"received": True})

    # -----------------------------------------------------------------------
    # Close
    # -----------------------------------------------------------------------

    def _handle_close(self, handler, payload: dict) -> None:
        """Receive close signal — from Host (peer side) or Operator (host side).

        Requires the close_token written to the Entity Store at process start.
        This prevents any external party from closing the channel — only the
        local Operator (with filesystem access) can read and supply the token.
        """
        import hmac as _hmac
        provided = payload.get("close_token", "")
        if not provided or not _hmac.compare_digest(provided, self._close_token):
            handler._forbidden("invalid close_token")
            return
        handler._ok({"closing": True})
        _log(f"[CMI] close signal received for {self.chan_id}")
        self._update_channel_status("closing")

        if self.role == "host":
            # Broadcast close to all peers
            close_msg = {
                "type": "CMI_CONTROL",
                "event": "channel_closing",
                "chan_id": self.chan_id,
                "ts": int(time.time()),
            }
            self._broadcast_to_peers(close_msg)
            # Give peers time to consolidate
            time.sleep(2)
            # Archive final BB
            self._archive_bb()

        # Notify CPE
        self._write_inbox_stimulus("CMI_CONTROL", {
            "event": "channel_closing",
            "chan_id": self.chan_id,
        })
        self._closing.set()

    def close_channel(self) -> None:
        """Called externally (e.g. by /cmi channel close) to initiate close."""
        self._handle_close_internal()

    def _handle_close_internal(self) -> None:
        self._update_channel_status("closing")
        self._write_inbox_stimulus("CMI_CONTROL", {
            "event": "channel_closing",
            "chan_id": self.chan_id,
        })
        self._closing.set()

    # -----------------------------------------------------------------------
    # BB read/write
    # -----------------------------------------------------------------------

    def _handle_bb_get(self, handler) -> None:
        entries = self._read_bb()
        handler._ok({"chan_id": self.chan_id, "entries": entries})

    def _append_bb(self, entry: dict) -> None:
        bb_path = self.layout.cmi_blackboard(self.chan_id)
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with bb_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _read_bb(self) -> list[dict]:
        bb_path = self.layout.cmi_blackboard(self.chan_id)
        if not bb_path.exists():
            return []
        entries = []
        for line in bb_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return entries

    def _archive_bb(self) -> None:
        """Host archives final BB digest after channel close."""
        entries = self._read_bb()
        import hashlib
        digest = hashlib.sha256(
            json.dumps(entries, separators=(",", ":")).encode()
        ).hexdigest()
        archive = {
            "chan_id": self.chan_id,
            "task": self._channel_cfg.get("task", ""),
            "closed_at": int(time.time()),
            "entry_count": len(entries),
            "bb_digest": f"sha256:{digest}",
        }
        archive_path = self.layout.cmi_channel_dir(self.chan_id) / "archive.json"
        archive_path.write_text(json.dumps(archive, indent=2), encoding="utf-8")
        _log(f"[CMI] BB archived: {self.chan_id} ({len(entries)} entries, digest={digest[:16]}...)")

    # -----------------------------------------------------------------------
    # Broadcast
    # -----------------------------------------------------------------------

    def _broadcast_to_peers(self, payload: dict, exclude: str = "") -> None:
        """Send payload to all enrolled peers (except exclude)."""
        with self._lock:
            peers = list(self._enrolled_peers)
        for peer in peers:
            if peer["node_identity"] == exclude:
                continue
            endpoint = peer.get("endpoint", "")
            if not endpoint:
                continue
            self._sign_and_post(endpoint + f"/channel/{self.chan_id}/stimulus", payload)

    def _sign_and_post(self, url: str, payload: dict) -> bool:
        """Sign payload and POST to url. Returns True on success."""
        if self._credential is None:
            return False
        from .identity import sign_message
        privkey = self._credential.get("privkey", "")
        signed = dict(payload)
        signed["from"] = self._credential.get("node_identity", "")
        data = json.dumps(signed, sort_keys=True).encode()
        sig = sign_message(privkey, data)
        signed["sig"] = sig
        body = json.dumps(signed).encode()
        try:
            req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:
            _log(f"[CMI] post failed to {url}: {exc}")
            return False

    # -----------------------------------------------------------------------
    # io/inbox/ — deliver stimuli to CPE
    # -----------------------------------------------------------------------

    def _write_inbox_stimulus(self, msg_type: str, payload: dict) -> None:
        """Write a CMI stimulus to io/inbox/ for the CPE to process (ACP format)."""
        from ..acp import make as acp_make, ACPEnvelope, encode, _MSG_SUFFIX
        import os
        data = {
            "type": msg_type,
            "channel_id": self.chan_id,
            **{k: v for k, v in payload.items() if k not in ("type", "channel_id", "chan_id")},
        }
        raw = acp_make(env_type="MSG", source="cmi", data=data)
        env = ACPEnvelope.from_dict(raw)
        ts_ms = int(time.time() * 1000)
        name = f"{ts_ms}_cmi_{msg_type.lower()}{_MSG_SUFFIX}"
        self.layout.spool_dir.mkdir(parents=True, exist_ok=True)
        spool_path = self.layout.spool_dir / name
        inbox_path = self.layout.inbox_dir / name
        spool_path.write_text(encode(env), encoding="utf-8")
        os.rename(str(spool_path), str(inbox_path))

    # -----------------------------------------------------------------------
    # State persistence
    # -----------------------------------------------------------------------

    def _save_participants(self) -> None:
        """Write participants.json to channel dir."""
        from ..store import atomic_write
        data = {
            "chan_id": self.chan_id,
            "local_role": self.role,
            "status": "active",
            "peers": self._enrolled_peers,
            "updated_at": int(time.time()),
        }
        atomic_write(self.layout.cmi_participants(self.chan_id), data)

    def _update_participants_status(self, status: str) -> None:
        from ..store import atomic_write
        p_path = self.layout.cmi_participants(self.chan_id)
        data: dict[str, Any] = {
            "chan_id": self.chan_id,
            "local_role": self.role,
            "status": status,
            "peers": self._enrolled_peers,
            "updated_at": int(time.time()),
        }
        if p_path.exists():
            try:
                existing = json.loads(p_path.read_text(encoding="utf-8"))
                existing.update(data)
                data = existing
            except Exception:
                pass
        atomic_write(p_path, data)

    def _update_channel_status(self, status: str) -> None:
        """Update channel status in baseline.cmi.channels."""
        from ..store import atomic_write, read_json
        if not self.layout.baseline.exists():
            return
        try:
            baseline = read_json(self.layout.baseline)
        except Exception:
            return
        channels = baseline.get("cmi", {}).get("channels", [])
        for ch in channels:
            if ch.get("id") == self.chan_id:
                ch["status"] = status
        atomic_write(self.layout.baseline, baseline)

    # -----------------------------------------------------------------------
    # Integrity fault logging
    # -----------------------------------------------------------------------

    def _log_mif(self, code: str, detail: str) -> None:
        """Log a Mesh Integrity Fault to integrity.log."""
        from ..acp import make as acp_encode
        from ..store import append_jsonl
        envelope = acp_encode(
            env_type="MSG",
            source="cmi",
            data={
                "type": "MESH_INTEGRITY_FAULT",
                "code": code,
                "chan_id": self.chan_id,
                "detail": detail,
                "ts": int(time.time()),
            },
        )
        append_jsonl(self.layout.integrity_log, envelope)
        _log(f"[CMI] {code}: {detail}")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _load_baseline(self) -> dict[str, Any]:
        from ..store import read_json
        try:
            return read_json(self.layout.baseline)
        except Exception:
            return {}

    def _load_credential(self) -> dict[str, Any] | None:
        from ..cmi.identity import load_cmi_credential
        return load_cmi_credential(self.layout)

    def _find_channel_cfg(self) -> dict[str, Any]:
        channels = self._cmi_cfg.get("channels", [])
        for ch in channels:
            if ch.get("id") == self.chan_id:
                return ch
        return {}

    def _find_trusted_peer(self, node_identity: str) -> dict[str, Any] | None:
        peers = self._cmi_cfg.get("trusted_peers", [])
        for p in peers:
            if p.get("node_identity") == node_identity:
                return p
        return None

    def _find_enrolled_peer(self, node_identity: str) -> dict[str, Any] | None:
        with self._lock:
            for p in self._enrolled_peers:
                if p.get("node_identity") == node_identity:
                    return p
        return None

    def _resolve_sender(self, node_identity: str) -> dict[str, Any] | None:
        """Return sender info for auth/role checks.

        The host entity is always a valid sender (role=host) — it never
        self-enrolls but must be able to send messages and BB contributions
        on channels it owns.  Enrolled peers are also valid senders.

        Returns a dict with keys: node_identity, pubkey, role.
        pubkey="" signals "skip signature verification" (self-sent by host).
        """
        my_ni = self._credential.get("node_identity", "") if self._credential else ""
        if node_identity and node_identity == my_ni:
            # Host sending on its own channel — no external sig verification needed
            return {"node_identity": my_ni, "pubkey": "", "role": "host"}
        return self._find_enrolled_peer(node_identity)

    def _verify(self, pubkey: str, payload: dict, sig: str) -> bool:
        if not pubkey or not sig:
            return False
        from .identity import verify_signature
        data = json.dumps(payload, sort_keys=True).encode()
        return verify_signature(pubkey, data, sig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main(sys.argv[1:])
