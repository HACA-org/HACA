# skill_create

Stages a new skill cartridge in `stage/<skill_name>/` for Endure installation.

## Parameters

- `skill_name` (required) — identifier used as directory and narrative filename.
- `manifest` (required) — JSON string with the skill manifest.
- `narrative` (required) — markdown text describing how the skill works.
- `script` (optional) — bash script content for `execute.sh`.

## Flow

1. Call skill_create with all params.
2. Submit ONE `evolution_proposal` to SIL:
   - `target_file`: `"stage/<skill_name>"`
   - `content`: the complete manifest JSON text (same as `manifest` param).
3. Endure installs manifest + narrative + execute.sh, rebuilds index, cleans stage/.

## Output

Prints staged file paths and the exact evolution_proposal to submit.
