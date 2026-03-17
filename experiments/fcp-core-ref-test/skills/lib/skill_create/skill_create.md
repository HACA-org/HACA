# skill_create

Stages a new skill cartridge in `stage/<skill_name>/` for Endure installation.

## Parameters

- `skill_name` (required) — identifier used as directory and narrative filename.
- `manifest` (required) — JSON string with the skill manifest.
- `narrative` (required) — markdown text describing how the skill works.
- `script` (optional) — bash script content for `execute.sh`.
- `hooks` (optional) — JSON object mapping hook event names to bash script content.
  Example: `{"on_boot": "#!/usr/bin/env bash\necho ready\n"}`

## Hook events

Hook scripts are installed to `hooks/<event>/<skill_name>.sh` and executed by the
relevant FCP component at these lifecycle points:

- `on_boot` — after boot, before first CPE cycle
- `on_session_close` — after closure_payload, before Endure
- `pre_skill` — before EXEC runs a skill (env: FCP_SKILL_NAME, FCP_SKILL_PARAMS)
- `post_skill` — after EXEC completes a skill (env: FCP_SKILL_NAME, FCP_SKILL_STATUS)
- `post_endure` — after Endure Protocol run (env: FCP_ENDURE_COMMITS)

All hook scripts receive: FCP_ENTITY_ROOT, FCP_SESSION_ID, FCP_HOOK_EVENT.
Non-zero exit code logs a warning and continues — hooks never block the entity.

## Flow

1. Call skill_create with all params.
2. Submit ONE `evolution_proposal` to SIL:
   - `target_file`: `"stage/<skill_name>"`
   - `content`: the complete manifest JSON text (same as `manifest` param).
3. Endure installs manifest + narrative + execute.sh + hooks, rebuilds index, cleans stage/.

## Output

Prints staged file paths and the exact evolution_proposal to submit.
