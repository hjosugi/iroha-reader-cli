"""Shell completions, generated from the parser itself.

Writing them by hand means they go stale the moment a flag changes,
so they are read off the same argparse parser the tool runs on.
"""

from __future__ import annotations

import argparse
import shlex

SHELLS = ("bash", "zsh", "fish")


def _first_sentence(text: str, limit: int = 60) -> str:
    """One short line of help, fit for a completion menu."""
    cleaned = " ".join((text or "").split()).replace("%%", "%")
    for stop in (". ", " (default", ", like", " -- ", ": "):
        head, _, _ = cleaned.partition(stop)
        cleaned = head
    if len(cleaned) > limit:
        # Cut at a word, not mid-word.
        cleaned = cleaned[:limit].rsplit(" ", 1)[0]
    return cleaned.strip().rstrip(".,")


def _options(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    # argparse keeps no public list of its actions.
    return [action for action in parser._actions if action.option_strings]


def _flags(parser: argparse.ArgumentParser) -> list[str]:
    return [flag for action in _options(parser) for flag in action.option_strings]


def _bash(parser: argparse.ArgumentParser, prog: str) -> str:
    flags = " ".join(_flags(parser))
    choices = "\n".join(
        f'        {"|".join(action.option_strings)})\n'
        f'            COMPREPLY=($(compgen -W "{" ".join(str(c) for c in action.choices)}"'
        f' -- "$current")); return 0;;'
        for action in _options(parser) if action.choices
    )
    return f"""# {prog} completion for bash.
#   {prog} --completion bash > /etc/bash_completion.d/{prog}
_{prog.replace("-", "_")}_complete() {{
    local current previous
    current="${{COMP_WORDS[COMP_CWORD]}}"
    previous="${{COMP_WORDS[COMP_CWORD-1]}}"

    case "$previous" in
{choices}
    esac

    if [[ "$current" == -* ]]; then
        COMPREPLY=($(compgen -W "{flags}" -- "$current"))
        return 0
    fi
    COMPREPLY=($(compgen -f -- "$current"))
}}
complete -o filenames -F _{prog.replace("-", "_")}_complete {prog}
"""


def _zsh(parser: argparse.ArgumentParser, prog: str) -> str:
    lines = []
    for action in _options(parser):
        description = _first_sentence(action.help or "")
        values = ""
        if action.choices:
            values = ":value:(" + " ".join(str(c) for c in action.choices) + ")"
        elif action.nargs != 0 and action.type is not None:
            values = ":value: "
        for flag in action.option_strings:
            lines.append(f"    {shlex.quote(flag + '[' + description + ']' + values)} \\")
    body = "\n".join(lines)
    return f"""#compdef {prog}
# {prog} completion for zsh.
#   {prog} --completion zsh > ~/.zfunc/_{prog}   (with ~/.zfunc in $fpath)
_arguments -s \\
{body}
    '*:document:_files -g "*.(md|markdown|epub|pdf|txt|text)"'
"""


def _fish(parser: argparse.ArgumentParser, prog: str) -> str:
    lines = [f"# {prog} completion for fish.",
             f"#   {prog} --completion fish > ~/.config/fish/completions/{prog}.fish",
             f"complete -c {prog} -f -a '(__fish_complete_path)'"]
    for action in _options(parser):
        parts = [f"complete -c {prog}"]
        for flag in action.option_strings:
            if flag.startswith("--"):
                parts.append(f"-l {flag[2:]}")
            else:
                parts.append(f"-s {flag[1:]}")
        if action.choices:
            values = " ".join(str(choice) for choice in action.choices)
            parts.append(f"-x -a {shlex.quote(values)}")
        elif action.nargs == 0:
            pass  # a switch takes nothing
        else:
            parts.append("-r")
        description = _first_sentence(action.help or "")
        if description:
            parts.append(f"-d {shlex.quote(description)}")
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def script(shell: str, parser: argparse.ArgumentParser, prog: str) -> str:
    """Return the completion script for one shell."""
    builders = {"bash": _bash, "zsh": _zsh, "fish": _fish}
    try:
        return builders[shell](parser, prog)
    except KeyError:
        raise ValueError(f"unknown shell: {shell}") from None
