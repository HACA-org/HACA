"""
Tool schema builders — FCP §6.

Builds the two representations of the available tool set sent to the CPE:

  build_tools_index()    — compact text list injected into the boot instruction block.
  build_tool_declarations() — full JSON schema list sent to the CPE API each cycle.

Both iterate the same skill index and load each manifest once via a shared
helper (_load_skill_entries), so the manifest-loading loop is not duplicated.
"""

from __future__ import annotations

from typing import Any

from .store import Layout, read_json


# ---------------------------------------------------------------------------
# Shared manifest loader
# ---------------------------------------------------------------------------

def _load_skill_entries(layout: Layout, index: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one dict per visible (non-operator) skill with manifest data.

    Each dict has: name, description, params_schema, required.
    """
    entries: list[dict[str, Any]] = []
    if not layout.skills_index.exists():
        return entries

    idx = index if index else read_json(layout.skills_index)
    for skill in idx.get("skills", []):
        if skill.get("class") == "operator":
            continue
        name = skill.get("name", "")
        if not name:
            continue
        manifest: dict[str, Any] = {}
        mrel = skill.get("manifest", "")
        if mrel:
            mpath = layout.root / mrel
            if mpath.exists():
                try:
                    manifest = read_json(mpath)
                except Exception:
                    pass
        params_schema = manifest.get("params", {"type": "object", "properties": {}})
        required: list[str] = (
            params_schema.get("required", []) if isinstance(params_schema, dict) else []
        )
        entries.append({
            "name": name,
            "description": manifest.get("description", f"Skill: {name}"),
            "params_schema": params_schema,
            "required": required,
        })
    return entries


# ---------------------------------------------------------------------------
# Boot instruction block — compact text index
# ---------------------------------------------------------------------------

# System tools: (name, description, required_params)
_SYSTEM_TOOL_ENTRIES: list[tuple[str, str, list[str]]] = [
    ("closure_payload",   "record full session outcome before closing",                             ["consolidation", "working_memory", "session_handoff"]),
    ("cmi_req",           "read state from an active CMI channel",                                  ["op", "chan_id"]),
    ("cmi_send",          "send a message to an active CMI channel",                                ["chan_id", "type", "content"]),
    ("evolution_proposal","propose structural change to entity (persona, skills, configs, scheduled tasks)", ["description", "changes"]),
    ("memory_recall",     "retrieve context from memory",                                           ["query"]),
    ("memory_write",      "persist information across sessions",                                    ["slug", "content"]),
    ("result_recall",     "retrieve truncated tool result by timestamp",                            ["ts"]),
    ("session_close",     "signal session complete",                                                []),
    ("skill_info",        "get full documentation for a skill",                                     ["skill"]),
]


def build_tools_index(layout: Layout, index: dict[str, Any]) -> str:
    """Build a compact alphabetical tools reference for the boot instruction block.

    Lists every tool available to the CPE: system tools plus skills from the
    index (class != 'operator'). Required params are noted inline.
    """
    entries: list[tuple[str, str, list[str]]] = list(_SYSTEM_TOOL_ENTRIES)

    for skill in _load_skill_entries(layout, index):
        entries.append((skill["name"], skill["description"], skill["required"]))

    entries.sort(key=lambda e: e[0])

    lines: list[str] = ["## Tools\n"]
    for name, desc, required in entries:
        params_str = ", ".join(f"{p} (required)" for p in required) if required else "none"
        lines.append(f"{name} — {desc}. params: {params_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CPE API call — full JSON schema declarations
# ---------------------------------------------------------------------------

def build_tool_declarations(layout: Layout, index: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the tool declarations sent to the CPE each cycle.

    Generates one tool per visible skill (class != 'operator') plus fixed
    system tools for memory, session control, and skill documentation.
    """
    tools: list[dict[str, Any]] = []

    # --- CMI tools ---
    tools.append({
        "name": "cmi_send",
        "description": "Send a message to an active CMI channel. Routes through the local CMI endpoint declared in the structural baseline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chan_id": {"type": "string", "description": "Channel identifier (e.g. chan_<uuid>)."},
                "type": {"type": "string", "enum": ["general", "peer", "bb"], "description": "Message type: 'general' (broadcast to all), 'peer' (directed, visible to all), 'bb' (Blackboard contribution, durable)."},
                "content": {"type": "string", "description": "Message content."},
                "to": {"type": "string", "description": "Target Node Identity for 'peer' messages. Required when type is 'peer'."},
            },
            "required": ["chan_id", "type", "content"],
        },
    })
    tools.append({
        "name": "cmi_req",
        "description": "Read state from an active CMI channel. 'bb' returns all Blackboard entries; 'status' returns channel status and enrolled participants.",
        "input_schema": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["bb", "status"], "description": "Operation: 'bb' to read the Blackboard, 'status' to get channel status and participants."},
                "chan_id": {"type": "string", "description": "Channel identifier (e.g. chan_<uuid>)."},
            },
            "required": ["op", "chan_id"],
        },
    })

    # --- memory tools ---
    tools.append({
        "name": "memory_recall",
        "description": "Retrieve context from memory before acting on requests that depend on prior sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for in memory."},
                "path": {"type": "string", "description": "Optional: restrict recall to a specific memory file path."},
            },
            "required": ["query"],
        },
    })
    tools.append({
        "name": "memory_write",
        "description": "Persist information that should survive across sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Short, stable, kebab-case identifier."},
                "content": {"type": "string", "description": "Content to persist."},
                "overwrite": {"type": "boolean", "description": "Set to true to overwrite an existing memory with this slug. If false (default) and the slug exists, the write is rejected and the existing content is returned for review."},
            },
            "required": ["slug", "content"],
        },
    })
    tools.append({
        "name": "result_recall",
        "description": "Retrieve the full payload of a truncated tool result from a previous cycle, by its timestamp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ts": {"type": "integer", "description": "The _ts_ms timestamp embedded in the truncated tool result."},
            },
            "required": ["ts"],
        },
    })

    # --- session control tools ---
    tools.append({
        "name": "session_close",
        "description": (
            "Signal that the session is complete. Always call closure_payload "
            "first to record the session outcome, then call this tool."
        ),
        "input_schema": {"type": "object", "properties": {}},
    })
    tools.append({
        "name": "closure_payload",
        "description": (
            "Record the full session outcome before closing. Call this immediately before session_close. "
            "Fields: consolidation (required), promotion (list of slugs), working_memory (list of {priority, path}), "
            "session_handoff ({pending_tasks, next_steps})."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "consolidation": {"type": "string", "description": "Narrative summary of insights and decisions from this session."},
                "promotion": {"type": "array", "items": {"type": "string"}, "description": "Slugs of episodic memories to promote to semantic knowledge."},
                "working_memory": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Artefacts to load at the next session, ordered by priority.",
                },
                "session_handoff": {
                    "type": "object",
                    "description": "Pending tasks and next steps for the following session.",
                },
            },
            "required": ["consolidation", "working_memory", "session_handoff"],
        },
    })
    tools.append({
        "name": "evolution_proposal",
        "description": (
            "Propose a structural change to the Entity Store. "
            "To install a custom skill: use skill_install op with the skill name (must be staged in /tmp/fcp-stage/<entity_id>/<name>/ and validated with skill_audit first). "
            "For other structural changes (persona files, configs): use json_merge, file_write, or file_delete ops. "
            "To propose a scheduled task: use cron_add op. "
            "Requires explicit Operator approval before taking effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Human-readable summary of the proposed change."},
                "changes": {
                    "type": "array",
                    "description": "List of structural changes to apply to the Entity Store.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["json_merge", "file_write", "file_delete", "skill_install", "cron_add"],
                                "description": "Operation: json_merge (partial update to a JSON file), file_write (create/replace a file), file_delete (remove a file), skill_install (promote a staged skill from /tmp/fcp-stage/<entity_id>/<name>/ to skills/<name>/ — use this to install custom skills, never file_write), cron_add (propose a new scheduled task).",
                            },
                            "target": {"type": "string", "description": "Path relative to entity root. Required for json_merge, file_write, file_delete. Not used for skill_install or cron_add."},
                            "name": {"type": "string", "description": "For skill_install: the skill name as it appears in /tmp/fcp-stage/<entity_id>/<name>/."},
                            "patch": {"type": "object", "description": "For json_merge: the fields to merge into the target JSON."},
                            "content": {"type": "string", "description": "For file_write: the full file content to write."},
                            "task": {"type": "string", "description": "For cron_add: clear, verifiable instruction the entity will execute when the schedule fires."},
                            "schedule": {"type": "string", "description": "For cron_add: cron expression (e.g. '0 9 * * 1-5')."},
                            "executor": {"type": "string", "enum": ["worker", "cpe"], "description": "For cron_add: 'worker' for read-only analysis tasks, 'cpe' for tasks that may write memory or call tools."},
                            "tools": {"type": "string", "description": "For cron_add: comma-separated list of skills/tools the task may use (leave empty if none)."},
                        },
                        "required": ["op"],
                    },
                },
            },
            "required": ["description", "changes"],
        },
    })

    # --- skill_info ---
    tools.append({
        "name": "skill_info",
        "description": "Retrieve the full documentation of a skill, including parameters and usage details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Name of the skill to inspect."},
            },
            "required": ["skill"],
        },
    })

    # --- one tool per visible skill ---
    for skill in _load_skill_entries(layout, index):
        tools.append({
            "name": skill["name"],
            "description": skill["description"],
            "input_schema": skill["params_schema"],
        })

    return tools
