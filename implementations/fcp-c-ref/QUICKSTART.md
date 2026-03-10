# FCP-Ref — Quick Start

This guide covers everything you need to start using FCP-Ref. No prior knowledge of HACA or FCP required.

---

## 1. Setup

**Clone and enter:**
```bash
git clone https://github.com/HACA-org/HACA
cd HACA/implementations/fcp-c-ref
```

**Configure a backend** (pick one):

```bash
# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Ollama (local, no key needed — just have Ollama running)
# ollama pull llama3
```

**Run:**
```bash
./sil.sh
```

On first run, FCP-Ref will walk you through a short setup. It will ask your name, a handle, and optionally your timezone. After that, it's ready.

---

## 2. Talking to the agent

Just type naturally. The agent maintains context across sessions — it remembers what you told it, what you worked on, and what it committed to doing.

```
You: remind me what we discussed about the auth refactor
Agent: [recalls from memory and summarizes]

You: save that the API keys rotate every 90 days
Agent: [stores to memory]

You: create a workspace for the billing module
Agent: [creates workspaces/billing-module/]
```

---

## 3. Skill shortcuts

Skills are invoked with a `.command` prefix. These bypass natural language processing and call the skill directly:

| Command | What it does |
|---------|--------------|
| `.save "content"` | Persist something to memory |
| `.recall query` | Search memory |
| `.swapin keyword` | Load archived memory into active context |
| `.snap "reason"` | Create a full system snapshot |
| `.snaps` | List available snapshots |
| `.summarize` | Summarize and close the current session |
| `.workspace name` | Create an isolated workspace |
| `.inbox` | Check incoming messages |
| `.recon` | Scan the host environment |
| `.endure` | Formal identity evolution (advanced) |

**Example:**
```
.snap "before the big refactor"
.save "database uses connection pooling — max 20 connections"
.recall deployment
```

---

## 4. Memory

The agent has persistent memory across sessions. You don't need to repeat yourself.

**What gets remembered automatically:**
- Things you explicitly ask it to save (`.save`)
- Decisions and outcomes from sessions (via `.summarize`)
- Your preferences

**Memory lives at two levels:**

- **Active context** (`memory/active_context/`) — loads at every boot, always available. High-priority knowledge. Use for things you need in every session.
- **Archive** (`memory/archive/`) — older sessions. Searchable but not automatically loaded. Use `.recall` or `.swapin` to bring it back.

**To make something always available:**
```
.save "project X is in Python 3.11, uses FastAPI and PostgreSQL"
```
The agent will store it and pin it to active context at the right priority.

---

## 5. Snapshots

A snapshot is a complete backup of the agent's cognitive state — memory, identity, skills, configuration.

```bash
.snap "before upgrading skills"
```

This creates a `.tar.gz` in `snapshots/`. To restore, use `skills/snapshot_restore.sh`.

**When to snapshot:**
- Before modifying skills
- Before identity evolution (`.endure`)
- Before any irreversible operation

---

## 6. Running modes

### Transparent Mode (default)
`./sil.sh` orchestrates the full cycle: assembles context, calls the LLM API, executes actions. The LLM backend is configured in `skills/llm_backends/`. Priority order: Claude → OpenAI → Ollama.

```bash
# Run one cycle
./sil.sh

# Skip drift probes (faster, for development)
SKIP_DRIFT=true ./sil.sh

# Dry run — assemble context but don't call LLM
DRY_RUN=true ./sil.sh
```

### Opaque Mode (IDE / AI assistant)
Open the project in an IDE with AI access (Claude Code, Cursor, GitHub Copilot Workspace). Paste `execute BOOT.md` into the prompt. The assistant reads `BOOT.md`, detects it has filesystem tools, and operates directly. No `sil.sh` needed — the assistant is the adapter.

**The system behaves identically in both modes.** Memory, skills, and identity work the same way. The difference is only in who acts as the adapter.

---

## 7. Adding skills

A skill is a directory under `skills/` with two files:

```
skills/my_skill/
├── manifest.json    # Name, command alias, parameters, sandbox
└── my_skill.sh      # The script that runs
```

**Minimal manifest:**
```json
{
    "name": "my_skill",
    "command": ".myskill",
    "version": "1.0",
    "capabilities": ["filesystem_write"],
    "security": {
        "sandbox": "workspaces_only",
        "write_targets": ["workspaces/"]
    },
    "params": {
        "input": {"type": "string", "required": true}
    }
}
```

Register it in `skills/index.json` under `skills` and add the alias to `aliases`. Then update `state/integrity.json` with the manifest hash.

---

## 8. Configuring backends

Backend scripts live in `skills/llm_backends/`. Each one exposes two behaviors:
- `--test` — exits 0 if the backend is available, 1 if not
- `<prompt>` — runs the prompt and prints the response to stdout

To add a new backend, copy an existing one and adapt. The dispatcher (`skills/llm_query.sh`) tries backends in the order listed in `BACKENDS`.

---

## 9. Files you should know

| File | What it is |
|------|-----------|
| `BOOT.md` | The system's instruction manual — what it reads on every start |
| `FIRST_BOOT.md` | First-run protocol — deleted after initialization |
| `persona/identity.md` | Who the agent is (immutable) |
| `persona/values.md` | How it makes decisions (immutable) |
| `persona/constraints.md` | What it will never do (immutable) |
| `skills/index.json` | All authorized skills and `.command` aliases |
| `state/integrity.json` | Cryptographic hashes of immutable files |
| `memory/session.jsonl` | Current session log |
| `memory/active_context/` | Memory loaded at every boot |
| `memory/preferences/operator.json` | Your operator profile |

---

## 10. What "immutable" means

Files in `persona/` and listed in `state/integrity.json` cannot be modified at runtime. If they change, the next boot aborts. This is intentional — it prevents the system from accidentally corrupting its own identity.

To evolve the identity formally, use `.endure`. It runs a validation protocol before committing any change.

---

## Next steps

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the system works under the hood: memory model, drift detection, ACP protocol, execution modes
- **[FCP Spec](../fcp-c-spec/)** — FCP formal specifications
- **[HACA Spec](../../spec/)** — HACA formal specifications

---

*Questions or issues: [github.com/HACA-org/HACA/issues](https://github.com/HACA-org/HACA/issues)*
