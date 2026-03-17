#!/bin/bash
# fcp-tui.sh — Interactive operator interface for FCP
#
# Provides a simple loop to communicate with the FCP entity.
# Usage: ./fcp-tui.sh

# Bootstrap: locate FCP_REF_ROOT
if [ -z "${FCP_REF_ROOT:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export FCP_REF_ROOT="$SCRIPT_DIR"
fi

source "$FCP_REF_ROOT/skills/lib/acp.sh"

clear
echo "==============================================================================="
echo "  Filesystem Cognitive Platform (FCP) — Operator Terminal  "
echo "==============================================================================="
echo "Type your message and press ENTER. Type 'exit' or 'quit' to close."
echo "-------------------------------------------------------------------------------"

# Function to display session history
show_history() {
    local session_file="$FCP_REF_ROOT/memory/session.jsonl"
    if [ ! -f "$session_file" ]; then
        return
    fi

    # Display the last 15 messages in a readable format
    tail -n 15 "$session_file" | while read -r line; do
        actor=$(echo "$line" | jq -r '.actor')
        type=$(echo "$line" | jq -r '.type')
        data=$(echo "$line" | jq -r '.data')
        
        # Parse data JSON if possible
        content=$(echo "$data" | jq -r '.content // .text // .message // empty' 2>/dev/null || echo "$data")
        
        case "$actor" in
            supervisor)
                if [[ "$content" == *"\"role\":\"assistant\""* ]]; then
                   # Assistant message inside supervisor actor
                   msg=$(echo "$content" | jq -r '.content' 2>/dev/null || echo "$content")
                   echo -e "\033[1;34m[ENTITY]\033[0m $msg"
                else
                   # Operator message
                   msg=$(echo "$content" | jq -r '.content' 2>/dev/null || echo "$content")
                   echo -e "\033[1;32m[YOU]\033[0m $msg"
                fi
                ;;
            sil)
                echo -e "\033[1;33m[SIL:$type]\033[0m $content"
                ;;
            el)
                echo -e "\033[1;31m[EL:$type]\033[0m $content"
                ;;
            *)
                echo -e "[$actor:$type] $content"
                ;;
        esac
    done
}

while true; do
    show_history
    echo -e "\n-------------------------------------------------------------------------------"
    read -p "> " USER_INPUT
    
    if [[ "$USER_INPUT" == "exit" || "$USER_INPUT" == "quit" ]]; then
        break
    fi

    if [ -z "$USER_INPUT" ]; then
        continue
    fi

    # Write user message to inbox
    # Wrap in JSON for the MSG type data
    PAYLOAD=$(jq -n --arg msg "$USER_INPUT" '{"role":"user","content":$msg}')
    acp_write "supervisor" "MSG" "$PAYLOAD" >/dev/null

    echo -e "\n\033[1;35m[SYSTEM] Invoking SIL...\033[0m"
    ./core/sil.sh --skip-drift  # Skip drift for faster TUI interaction in example
    
    clear
    echo "==============================================================================="
    echo "  Filesystem Cognitive Platform (FCP) — Operator Terminal  "
    echo "==============================================================================="
done

echo "Closing session."
