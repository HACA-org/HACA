#!/bin/bash
# install.sh — FCP (Filesystem Cognitive Platform) Reference Implementation
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HACA-org/HACA/main/implementations/fcp-ref/install.sh | bash
#
# To uninstall:
#   rm -rf ~/.fcp
#   rm ~/.local/bin/fcp

set -euo pipefail

# ── Visual Constants (Matching fcp_base/ui.py) ───────────────────────────────

RESET="\033[0m"
BOLD_CYAN="\033[1;96m"
W=60

# ── UI Helpers ───────────────────────────────────────────────────────────────

hr() {
    local label="${1:-}"
    if [ -n "$label" ]; then
        local label_len=${#label}
        local pad=$((W - label_len - 4))
        [ $pad -lt 0 ] && pad=0
        printf "\n  ── %s $(printf '%.0s─' $(seq 1 $pad))\n" "$label"
    else
        printf "  $(printf '%.0s─' $(seq 1 $W))\n"
    fi
}

ok()   { printf "  ${BOLD_CYAN}[√]${RESET} %s\n" "$1"; }
warn() { printf "  ${BOLD_CYAN}[!]${RESET} %s\n" "$1"; }
err()  { printf "  ${BOLD_CYAN}[ERROR]${RESET} %s\n" "$1"; }
info() { printf "  %s\n" "$1"; }

pick_yes_no() {
    local prompt="$1"
    local default="$2" # "true" or "false"
    local current
    current=$([ "$default" = "true" ] && echo 0 || echo 1)

    printf "  %s\n" "$prompt" >&2

    while true; do
        if [ "$current" -eq 0 ]; then
            printf "  ${BOLD_CYAN}> Yes${RESET}\n" >&2
            printf "    No\n" >&2
        else
            printf "    Yes\n" >&2
            printf "  ${BOLD_CYAN}> No${RESET}\n" >&2
        fi

        # Read a single keypress from the terminal (fixes curl | bash piping issues)
        read -rsn3 key < /dev/tty

        # Check for arrow keys
        if [[ "$key" == $'\x1b[A' || "$key" == $'\x1b[B' ]]; then
            current=$((1 - current))
            printf "\033[2A" >&2 # Move cursor up 2 lines
        elif [[ "$key" == "" ]]; then
            # Clean up: move up and print the selection permanently
            printf "\033[2A\033[J" >&2 # Move up 2 and clear below
            if [ "$current" -eq 0 ]; then
                printf "  ${BOLD_CYAN}Yes${RESET}\n" >&2
                return 0
            else
                printf "  ${BOLD_CYAN}No${RESET}\n" >&2
                return 1
            fi
        else
            printf "\033[2A" >&2
        fi
    done
}

ask() {
    local prompt="$1"
    local default="${2:-}"
    local hint=""
    [ -n "$default" ] && hint=" [$default]"

    # Redirect prompt to stderr and read value from the terminal (fixes curl | bash piping issues)
    printf "  %s%s: " "$prompt" "$hint" >&2
    read -r val < /dev/tty
    echo "${val:-$default}"
}


# ── Main Installer ───────────────────────────────────────────────────────────

clear || true
printf "\n"
hr "FCP Installer"
info "Filesystem Cognitive Platform — Reference Implementation"
info "HACA — Host-Agnostic Cognitive Architecture v1.0"
hr ""
info "This script prepares your host and syncs the FCP-Ref"
info "implementation using Sparse Checkout from github.com/HACA-org/HACA."
printf "\n"

# ── Step 1: Environment ──────────────────────────────────────────────────────
hr "1. Environment"
printf "\n"

# Python check
if command -v python3 &> /dev/null; then
    read -r py_major py_minor py_micro < <(python3 -c \
        'import sys; v=sys.version_info; print(v.major, v.minor, v.micro)')
    py_ver="${py_major}.${py_minor}.${py_micro}"

    if [ "$py_major" -eq 3 ] && [ "$py_minor" -ge 11 ]; then
        ok "Python $py_ver detected."
    else
        err "Python $py_ver found, but >= 3.11 is required."
        exit 1
    fi
else
    err "Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

# Git check
if command -v git &> /dev/null; then
    ok "Git detected."
else
    err "Git is not installed. Git is required to fetch the FCP reference."
    exit 1
fi

# uv check (optional — needed for fcp-mcp MCP server)
if command -v uv &> /dev/null; then
    ok "uv detected (required for fcp-mcp MCP server)."
else
    warn "uv not found. Required for the FCP MCP Server (fcp-mcp)."
    info "Install it later with: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# Network check
if ! curl -fsSL --max-time 5 https://github.com > /dev/null 2>&1; then
    err "Cannot reach github.com. Check your internet connection."
    exit 1
fi
ok "Network reachable."
printf "\n"

# ── Step 2: Destination ──────────────────────────────────────────────────────
hr "2. Destination"
printf "\n"
info "Where should the FCP repository be stored on your host?"
info "Default path: $HOME/.fcp"
printf "\n"
INSTALL_PATH=$(ask "  (Leave blank to use default)" "$HOME/.fcp")
INSTALL_PATH="${INSTALL_PATH/#\~/$HOME}"
printf "\n"

# ── Step 3: Setup ────────────────────────────────────────────────────────────
hr "3. Command Setup"
printf "\n"
info "To run 'fcp' from any directory, a symbolic link can be"
info "created in your local binary folder (~/.local/bin)."
printf "\n"
SET_ALIAS=false
if pick_yes_no "Create global 'fcp' command?" "true"; then
    SET_ALIAS=true
fi
printf "\n"

# ── Step 4: Installation ─────────────────────────────────────────────────────
hr "4. Syncing Repository"
printf "\n"

REPO_URL="https://github.com/HACA-org/HACA.git"
REF_PATH="implementations/fcp-ref"

if [ -d "$INSTALL_PATH" ]; then
    info "Target directory exists. Updating..."
    if [ -d "$INSTALL_PATH/.git" ]; then
        # Ensure sparse-checkout is still configured correctly
        git -C "$INSTALL_PATH" sparse-checkout set "$REF_PATH" --quiet 2>/dev/null || true
        if git -C "$INSTALL_PATH" pull origin main --quiet; then
            ok "Repository updated."
        else
            warn "Git pull failed. Proceeding with existing files."
        fi
    else
        warn "$INSTALL_PATH exists but is not a git repository. Skipping sync."
    fi
else
    info "Initiating Sparse Checkout (fetching only fcp-ref)..."

    # 1. Clone with --sparse and filtered blobs to minimize footprint
    git clone --depth 1 --filter=blob:none --sparse "$REPO_URL" "$INSTALL_PATH" --quiet

    # 2. Specifically enable only the fcp-ref implementation path
    git -C "$INSTALL_PATH" sparse-checkout set "$REF_PATH"

    ok "FCP-Ref synced successfully to $INSTALL_PATH"
fi

# Locate the actual executable within the sparse subtree
REAL_FCP_EXE="$INSTALL_PATH/$REF_PATH/fcp"

if [ -f "$REAL_FCP_EXE" ]; then
    chmod +x "$REAL_FCP_EXE"
else
    err "Could not find 'fcp' entrypoint at $REAL_FCP_EXE"
    exit 1
fi

# Create (or refresh) symlink if requested
if [ "$SET_ALIAS" = true ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$REAL_FCP_EXE" "$HOME/.local/bin/fcp"
    ok "Link created: ~/.local/bin/fcp -> $REAL_FCP_EXE"
fi
printf "\n"

# ── Step 5: Finalizing ───────────────────────────────────────────────────────
hr "5. Summary"
printf "\n"
ok "Installation complete!"
hr ""
info "FCP Root     : $INSTALL_PATH"
info "Active Impl  : $REF_PATH"
if [ "$SET_ALIAS" = true ]; then
    info "Global command: fcp"
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "$HOME/.local/bin is NOT in your PATH."
        info "Add this to your ~/.bashrc or ~/.zshrc:"
        info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
fi
hr ""
info "Quick Start:"
info "  1. run: fcp init   (creates your entity at ~/.fcp/<entity_id>/)"
info "  2. cd into your project folder"
info "  3. run: fcp        (entity boots with that folder as workspace)"
printf "\n"
