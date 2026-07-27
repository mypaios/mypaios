#!/usr/bin/env bash
# Tab-completion for the `paios` umbrella + every `paios-*` CLI.
#
# Source from your shell rc:
#     source /path/to/paios-ui/scripts/_completion/paios.bash
#
# Or wire it once per machine:
#     sudo install -m 644 paios.bash /etc/bash_completion.d/paios
#
# What it does:
#   - On the first word after `paios`, complete with the list of
#     subcommands (`mail`, `calendar`, ...).
#   - On subsequent words, complete with the subcommand's first-token
#     subcommands (`list`, `show`, ...) which we cache by parsing the
#     tool's own --help output. Updates lazily; refresh by running
#     `_paios_refresh_cache`.
#   - Same completion works for the individual `paios-foo` scripts.

_paios_scripts_dir() {
    # Resolve the scripts/ dir from the script that sources us. We assume
    # the user sourced the file directly out of scripts/_completion/.
    local self="${BASH_SOURCE[0]}"
    while [ -L "$self" ]; do self=$(readlink "$self"); done
    cd "$(dirname "$self")/.." && pwd
}

declare -A _PAIOS_SUBS_CACHE=()

_paios_refresh_cache() {
    local dir="$(_paios_scripts_dir)"
    _PAIOS_SUBS_CACHE=()
    # Prefer the project venv's Python so deps (bcrypt, sqlalchemy, ...)
    # resolve. Falls back to system `python3` for container installs.
    local py="$dir/../venv/bin/python"
    [ -x "$py" ] || py="$(command -v python3)"
    local f
    for f in "$dir"/paios-*; do
        [ -x "$f" ] || continue
        case "$f" in *.bak|*.pyc|*.pre-*) continue ;; esac
        local name="$(basename "$f")"
        local sub="${name#paios-}"
        local help_out
        help_out=$("$py" "$f" --help 2>/dev/null) || continue
        local commands
        commands=$(echo "$help_out" | grep -oE '\{[a-z0-9_,-]+\}' | head -1 \
            | tr -d '{}' | tr ',' ' ')
        _PAIOS_SUBS_CACHE[$sub]="$commands"
    done
}

_paios_complete() {
    [ ${#_PAIOS_SUBS_CACHE[@]} -eq 0 ] && _paios_refresh_cache

    local cur="${COMP_WORDS[COMP_CWORD]}"
    local cmd="${COMP_WORDS[0]}"

    # `paios <tab>` → list every subcommand
    if [ "$cmd" = "paios" ]; then
        if [ "$COMP_CWORD" -eq 1 ]; then
            local subs="${!_PAIOS_SUBS_CACHE[@]} help"
            COMPREPLY=($(compgen -W "$subs" -- "$cur"))
            return 0
        fi
        # `paios foo <tab>` — complete with foo's own subcommands
        local sub="${COMP_WORDS[1]}"
        # `paios help <tab>` lists every subcommand
        if [ "$sub" = "help" ] && [ "$COMP_CWORD" -eq 2 ]; then
            COMPREPLY=($(compgen -W "${!_PAIOS_SUBS_CACHE[*]}" -- "$cur"))
            return 0
        fi
        if [ "$COMP_CWORD" -eq 2 ]; then
            COMPREPLY=($(compgen -W "${_PAIOS_SUBS_CACHE[$sub]}" -- "$cur"))
            return 0
        fi
        return 0
    fi

    # Direct `paios-foo <tab>` (no umbrella)
    local sub="${cmd#paios-}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=($(compgen -W "${_PAIOS_SUBS_CACHE[$sub]}" -- "$cur"))
        return 0
    fi
}

# Register the completion for every paios-* script + the umbrella.
complete -F _paios_complete paios
for f in "$(_paios_scripts_dir)"/paios-*; do
    [ -x "$f" ] || continue
    case "$f" in *.bak|*.pyc|*.pre-*) continue ;; esac
    complete -F _paios_complete "$(basename "$f")"
done
