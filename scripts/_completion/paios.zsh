#compdef paios paios-backup paios-calendar paios-contacts paios-cookbook paios-docs paios-gallery paios-mail paios-mcp paios-memory paios-notes paios-personal paios-preset paios-research paios-sessions paios-signature paios-skills paios-tasks paios-theme paios-webhook
# Zsh tab-completion for the paios umbrella + sub-CLIs.
#
# Drop in any directory on $fpath, e.g.:
#     fpath=(/path/to/paios-ui/scripts/_completion $fpath)
#     autoload -U compinit; compinit
#
# Then `paios <tab>` completes subcommands; `paios mail <tab>`
# completes mail subcommands; `paios-mail <tab>` works the same.

_paios_scripts_dir() {
    local self="${(%):-%x}"
    while [[ -L "$self" ]]; do self="$(readlink "$self")"; done
    cd "${self:h}/.." && pwd
}

typeset -gA _paios_subs

_paios_refresh() {
    _paios_subs=()
    local dir="$(_paios_scripts_dir)"
    local py="$dir/../venv/bin/python"
    [[ -x "$py" ]] || py="$(command -v python3)"
    local f sub help_out commands
    for f in "$dir"/paios-*; do
        [[ -x "$f" ]] || continue
        case "$f" in
            *.bak|*.pyc|*.pre-*) continue ;;
        esac
        sub="${${f:t}#paios-}"
        help_out=$("$py" "$f" --help 2>/dev/null) || continue
        commands=$(echo "$help_out" | grep -oE '\{[a-z0-9_,-]+\}' | head -1 \
            | tr -d '{}' | tr ',' ' ')
        _paios_subs[$sub]="$commands"
    done
}

_paios() {
    [[ ${#_paios_subs} -eq 0 ]] && _paios_refresh

    local cmd="${words[1]}"

    if [[ "$cmd" == "paios" ]]; then
        if (( CURRENT == 2 )); then
            local -a subs=(${(k)_paios_subs} help)
            _describe 'subcommand' subs
            return
        fi
        local sub="${words[2]}"
        if [[ "$sub" == "help" ]] && (( CURRENT == 3 )); then
            local -a subs=(${(k)_paios_subs})
            _describe 'subcommand' subs
            return
        fi
        if (( CURRENT == 3 )); then
            local -a sc=(${(s/ /)_paios_subs[$sub]})
            _describe 'command' sc
            return
        fi
        return
    fi

    # paios-foo <tab>
    local sub="${cmd#paios-}"
    if (( CURRENT == 2 )); then
        local -a sc=(${(s/ /)_paios_subs[$sub]})
        _describe 'command' sc
        return
    fi
}

_paios "$@"
