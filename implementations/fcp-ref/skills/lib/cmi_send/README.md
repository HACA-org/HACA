# cmi_send

Send a message to an active CMI channel. Routes through the local CMI endpoint declared in the structural baseline (`cmi.endpoint`).

Messages are broadcast to all channel participants. The channel must be active and declared in the structural baseline.

## Message types

- `general` — broadcast coordination message, no specific recipient. Ephemeral: discarded at channel close.
- `peer` — directed coordination message with a declared target (`to`). Visible to all participants. Ephemeral.
- `bb` — Blackboard contribution. Durable: sequenced by the Host and persisted for the channel's lifetime.

## Examples

```
→ cmi_send({ "chan_id": "chan_abc", "type": "general", "content": "Analysis complete. See BB for results." })
→ cmi_send({ "chan_id": "chan_abc", "type": "bb", "content": "Summary: ..." })
→ cmi_send({ "chan_id": "chan_abc", "type": "peer", "to": "sha256:...", "content": "Can you verify this?" })
```

## Parameters

- `chan_id` (required) — channel identifier.
- `type` (required) — `general`, `peer`, or `bb`.
- `content` (required) — message content.
- `to` — target Node Identity; required when `type` is `peer`.
