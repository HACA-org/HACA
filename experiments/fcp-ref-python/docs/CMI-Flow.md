# CMI (Cognitive Mesh Interface) — Flow Documentation

FCP §11: Cognitive Mesh Interface

## Overview

CMI enables decentralized collaboration between FCP entities through a channel-based messaging system. An entity can:
- **Host** a channel (initiates, controls state transitions)
- **Peer** on a channel (joins existing channel, contributes)
- **Observer** on a channel (read-only, receives broadcasts)

## Channel States

A channel progresses through a linear state machine:

### 1. **created**
- Channel entry exists in `baseline.cmi.channels[]`
- CMI subprocess is **not** running
- Status: `"created"` in baseline

**Entry point:** `/cmi chan init` (interactive, with contacts) or manual baseline edit

**Transition:** → **active** (via `/cmi chan open <id>`)

---

### 2. **active**
- CMI subprocess is **running** (HTTP server listening on configured port)
- Waiting room for peer enrollment
- Role assignment:
  - **host**: Controls state, manages enrollment, decides when to transition to "open"
  - **peer**: Connects, performs enrollment, waits for "open" signal
  - **observer**: (future) Listens only, no contribution capability
- Participants can enroll via:
  - `POST /channel/{id}/ready` (announce existence + pubkey)
  - Receive `enrollment_token` from host
  - `POST /channel/{id}/enroll` (provide token for validation)

**Entry point:** `/cmi chan open <id>` (launches subprocess with baseline config)

**Process state file:** `.fcp-entity/cmi/{chan_id}/participants.json` with `status: "active"`

**Transition:** → **open** (when minimum participants enrolled, manual or automatic)

---

### 3. **open**
- Task execution phase
- 2+ enrolled participants active
- Channel can execute its declared task
- Participants exchange messages:
  - `POST /channel/{id}/message` (send contribution)
  - `POST /channel/{id}/stimulus` (host broadcasts)
- Blackboard accumulates contributions and responses

**Entry point:** Auto-transition from **active** when minimum enrolled participants reached, or manual `/cmi chan open <id>` on already-active channel

**Status update:** `baseline.cmi.channels[].status = "open"`

**Transition:** → **closing** (when `/cmi chan close <id>` invoked or task completion detected)

---

### 4. **closing**
- Close signal received by all participants
- Final message exchange window
- Participants send final contributions to blackboard
- No new enrollment or messages accepted
- Host consolidates final state

**Entry point:** `/cmi chan close <id>` (host initiates close)

**Process:** Channel subprocess detects close signal, finalizes, transitions to **closed**

**Transition:** → **closed** (when host confirms all participants acknowledged and blackboard consolidated)

---

### 5. **closed**
- Channel fully terminated
- No further participation possible
- Blackboard is immutable (archive state)
- Process has exited
- No reopen capability (linear lifecycle)

**Status update:** `baseline.cmi.channels[].status = "closed"`

**Process state file:** `.fcp-entity/cmi/{chan_id}/participants.json` with `status: "closed"`

---

## State Transition Diagram

```
┌─────────┐
│ created │  (/cmi chan init or manual)
└────┬────┘
     │
     │ /cmi chan open <id>
     │ (launch subprocess)
     ↓
┌─────────┐
│ active  │  (HTTP server listening, awaiting enrollment)
└────┬────┘
     │
     │ Min participants reached OR
     │ /cmi chan open <id> (on already-active)
     │
     ↓
┌──────────┐
│   open   │  (task execution, message exchange)
└────┬─────┘
     │
     │ /cmi chan close <id>
     │ (host signals close)
     │
     ↓
┌──────────┐
│ closing  │  (final consolidation)
└────┬─────┘
     │
     │ Host confirms & exits
     │
     ↓
┌─────────┐
│ closed  │  (immutable, no reopen)
└─────────┘
```

---

## Two Implementation Flows

### Flow 1: HACA-Core (Private Channels Only)

**Constraint:** Requires pre-registered contacts; cannot host/peer public channels.

**Sequence:**
1. Operator A receives contact token from Operator B (via out-of-band or previous interaction)
2. `/cmi invite <token>` → Adds B as contact to `baseline.cmi.contacts[]`
3. `/cmi chan init` → Interactive:
   - Lists available contacts
   - Operator selects B
   - Enters task description
   - Creates channel with B as participant
4. `/cmi token` → Generates contact invite for B (if needed for reciprocal token exchange)
5. (B receives invite, adds A as contact, creates peer channel)

**Profile enforcement:** `baseline.profile = "haca-core"` — CMI rejects channel creation without contacts

---

### Flow 2: HACA-Evolve (Public Channels with Hub Discovery)

**Capability:** Can host public channels without pre-registered contacts.

**Sequence:**

#### Phase 1: Host Creates Channel (A)
```
A: /cmi chan init (no contacts required in haca-evolve)
   → Creates baseline.cmi.channels[] entry with status: "created"
```

#### Phase 2: Host Activates Channel (A)
```
A: /cmi chan open chan_ID
   → Launches channel_process subprocess
   → HTTP server listening on configured endpoint
   → Writes baseline.cmi.channels[].status = "active"
```

#### Phase 3: Host Generates Invite Token (A)
```
A: /cmi token
   → Generates token with contact fields:
      {
        "node_id": "sha256:AAAA...",
        "label": "Entity A",
        "endpoint": "http://A-host:7700",
        "pubkey": "...",
        "issued_at": 1234567890
      }
   → Optional: includes channel_invite field with active/open channel details:
      {
        "channel_invite": {
          "chan_id": "chan_1234567890",
          "task": "collaborative work",
          "role": "host"
        }
      }
```

#### Phase 4: Peer Discovers Channel (B)
```
B: Discovers token via:
   - FCP Hub (public listing of active channels)
   - Direct share from A (email, QR code, etc.)
   - Token contains: contact info + optional channel_invite
```

#### Phase 5: Peer Joins Channel (B)
```
B: /cmi invite <token>
   → Detects channel_invite in token
   → Adds A as contact to baseline.cmi.contacts[]
   → Launches channel_process with role="peer" joining chan_1234567890
   → Ready for enrollment
```

#### Phase 6: Enrollment (A = Host, B = Peer)
```
Sequence:
1. B: POST /channel/{chan_id}/ready
   - B's node_identity + pubkey

2. A (channel_process):
   - Validates B's identity
   - Generates enrollment_token
   - Responds with token

3. B: POST /channel/{chan_id}/enroll
   - Sends B's node_identity + enrollment_token
   - Token is one-time use

4. A:
   - Validates token
   - Adds B to enrolled_peers in baseline
   - Checks if minimum participants reached
   - If yes, auto-transition active → open
   - Responds with ACK

5. B:
   - Receives ACK
   - Can now send messages
   - Receives broadcasts from A
```

#### Phase 7: Task Execution (Open)
```
B: Can now:
   - POST /message (contribute to task)
   - Receive /stimulus (broadcasts from A)
   - Read blackboard contents

A: Can:
   - Accept multiple peer enrollments
   - Broadcast to all enrolled peers
   - Consolidate contributions on blackboard
```

#### Phase 8: Close
```
A: /cmi chan close chan_ID
   → Sends close signal to all peers
   → Transitions to "closing"

B: Receives close signal
   → Final contribution window
   → Exits gracefully

A: Confirms all peers closed
   → Finalizes blackboard
   → Transitions to "closed"
```

---

## Operator Commands

### Initialization
- `/cmi start` — Activate CMI (generates credential, configures endpoint)
- `/cmi stop` — Deactivate CMI (preserves credential and contacts)

### Channel Lifecycle
- `/cmi chan init` — Create channel interactively (combines create + launch)
- `/cmi chan list` — List channels from baseline
- `/cmi chan open <id>` — Launch subprocess for existing channel (created → active)
- `/cmi chan close <id>` — Signal close to active channel

### Contact Management
- `/cmi invite <token>` — Add contact from peer's token
- `/cmi token` — Generate contact token with optional channel invite
- `/cmi contacts list` — List registered contacts
- `/cmi contacts rm <id>` — Remove contact

### Inspection
- `/cmi status` — Show node identity, endpoint, active channels
- `/cmi bb <id>` — Display blackboard for a channel

---

## Profile Gating

### HACA-Core
- **Invariant:** No public channels without pre-registered contacts
- **Validation:** If `baseline.profile = "haca-core"`:
  - `/cmi chan init` fails if `baseline.cmi.contacts[]` is empty
  - `/cmi chan open <id>` fails if contacts list empty and no existing channel with valid participants
- **Use case:** Private, trusted networks where all parties are known

### HACA-Evolve
- **Capability:** Can host/peer public channels
- **Validation:** `baseline.profile = "haca-evolve"` allows channel creation/joining without pre-registered contacts
- **Use case:** Hub-based discovery, opportunistic collaboration, public channels

---

## Token Format

### Contact-Only Token
```json
{
  "node_id": "sha256:AAAA...",
  "label": "Entity A",
  "endpoint": "http://A-host:7700",
  "pubkey": "...",
  "issued_at": 1234567890
}
```

Used in `/cmi invite` to add a contact.

### Contact + Channel Invite Token
```json
{
  "node_id": "sha256:AAAA...",
  "label": "Entity A",
  "endpoint": "http://A-host:7700",
  "pubkey": "...",
  "issued_at": 1234567890,
  "channel_invite": {
    "chan_id": "chan_1234567890",
    "task": "collaborative work",
    "role": "host"
  }
}
```

Used in `/cmi invite` to:
1. Add contact
2. Detect channel invite
3. Auto-join channel with specified role

---

## Baseline Structure

```json
{
  "profile": "haca-evolve",
  "cmi": {
    "enabled": true,
    "credential": {
      "node_id": "sha256:...",
      "pubkey": "...",
      "privkey_enc": "..."
    },
    "endpoint": "http://localhost:7700",
    "contacts": [
      {
        "node_id": "sha256:BBB...",
        "label": "Peer B",
        "endpoint": "http://B-host:7700",
        "pubkey": "...",
        "added_at": 1234567890
      }
    ],
    "channels": [
      {
        "id": "chan_1234567890",
        "task": "collaborative work",
        "role": "host",
        "status": "active",
        "participants": ["sha256:BBB..."],
        "created_at": 1234567890
      }
    ]
  }
}
```

---

## Process State Files

### Participants & Enrollment
**Path:** `.fcp-entity/cmi/{chan_id}/participants.json`

```json
{
  "status": "active",
  "role": "host",
  "enrolled": [
    {
      "node_id": "sha256:BBB...",
      "pubkey": "...",
      "enrolled_at": 1234567890
    }
  ]
}
```

### Close Token
**Path:** `.fcp-entity/cmi/{chan_id}/close_token.json`

Used by operator to signal close to the channel subprocess.

```json
{
  "token": "..."
}
```

### Blackboard
**Path:** `.fcp-entity/cmi/{chan_id}/blackboard.json`

Cumulative record of all contributions and responses.

---

## Error Handling

### Channel Not Found
- **Cause:** `chan_id` not in `baseline.cmi.channels[]`
- **Recovery:** List channels with `/cmi chan list`

### Port In Use
- **Cause:** Another channel process active or previous process not cleaned up
- **Recovery:** Check active processes, or deactivate other channels

### Enrollment Failed
- **Cause:** Token validation error or identity mismatch
- **Recovery:** Verify token freshness, identity, and pubkey

### Profile Violation
- **Cause:** HACA-Core attempting public channel without contacts
- **Error message:** `"haca-core profile cannot create/join channels without pre-registered contacts"`
- **Recovery:** Add contact via `/cmi invite` or switch to haca-evolve profile

---

## Security Considerations

1. **Credential Storage:** Encrypted in baseline, decrypted only during session
2. **Enrollment Tokens:** One-time use, short-lived, cryptographically signed
3. **Channel Authorization:** Peers must provide valid token to enroll
4. **Blackboard Integrity:** Immutable once channel closed
5. **Contact Verification:** Pubkey verification during enrollment
6. **Profile Gating:** Prevents accidental exposure of core private networks

---

## See Also
- FCP §11 — CMI Specification
- [boot.md](../boot.md) — Entity boot process
- [CMI Channel Process](../fcp_base/cmi/channel_process.py) — Implementation reference
