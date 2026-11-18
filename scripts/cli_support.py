"""Shared metadata and parser-derived shell completion for public commands."""
import argparse
import os
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMAND = None


def can_prompt():
    return not os.environ.get("CI") and sys.stdin.isatty() and sys.stdout.isatty()


def version():
    return (ROOT / 'VERSION').read_text().strip()


def prepare(command):
    """Answer version requests before loading command implementations or user state."""
    global COMMAND
    COMMAND = command
    arguments = sys.argv[1:]
    cached_help = ROOT / 'config/cli-help' / (command + '.txt')
    if arguments in (['--help'], ['-h']) and not os.environ.get('LINUX_SETUP_BUILD_CLI') and cached_help.is_file():
        print(cached_help.read_text(), end='')
        raise SystemExit(0)
    if arguments == ['--version']:
        print(f'{command} {version()}')
        raise SystemExit(0)


class CompletionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(completion(parser, values), end='')
        parser.exit()


class HelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, width=88)


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        if 'prog' not in kwargs:
            name = Path(sys.argv[0]).name
            kwargs['prog'] = COMMAND or {'setup.py': 'install.sh', 'uninstall.py': 'uninstall.sh'}.get(name, name)
        kwargs.setdefault('formatter_class', HelpFormatter)
        super().__init__(*args, **kwargs)
        self.add_argument('--version', action='version', version='%(prog)s ' + version())
        self.add_argument('--completion', choices=('bash', 'zsh', 'fish'), action=CompletionAction,
                          help='Print a shell completion script without changing files')


def schema(parser):
    """Read real parser actions, so completions follow existing command signatures."""
    contexts, transitions, values = {}, [], {}
    def visit(current, context):
        candidates = []
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    candidates.append(name)
                    path = (context + ' ' + name).strip()
                    transitions.append((context + '|' + name, path))
                    visit(child, path)
            elif action.help != argparse.SUPPRESS:
                candidates.extend(action.option_strings)
                if action.choices:
                    choices = [str(value) for value in action.choices]
                    if action.option_strings:
                        for option in action.option_strings:
                            values[context + '|' + option] = choices
                    else:
                        candidates.extend(choices)
        contexts[context] = list(dict.fromkeys(candidates))
    visit(parser, '')
    return contexts, transitions, values


def completion(parser, shell):
    command = parser.prog
    identifier = '_linux_setup_' + re.sub(r'[^a-zA-Z0-9_]', '_', command)
    contexts, transitions, values = schema(parser)
    q = shlex.quote
    if shell == 'fish':
        helper = identifier + '_context'
        lines = [f'function {helper}', '    set -l context __root__', '    set -l tokens (commandline -opc)', '    for word in $tokens[2..-1]', '        switch "$context|$word"']
        for pattern, target in transitions:
            fish_pattern = ('__root__' + pattern) if pattern.startswith('|') else pattern
            lines += ['            case ' + q(fish_pattern), '                set context ' + q(target)]
        lines += ['        end', '    end', '    printf "%s\\n" "$context"', 'end']
        for context, words in contexts.items():
            condition = f'test ({helper}) = {q(context or "__root__")}'
            for word in words:
                if word.startswith('--'):
                    spec = '-l ' + q(word[2:])
                elif word.startswith('-') and len(word) == 2:
                    spec = '-s ' + q(word[1:])
                else:
                    spec = '-a ' + q(word)
                options = values.get(context + '|' + word)
                if options:
                    spec += ' -r -a ' + q(' '.join(options))
                lines.append(f'complete -c {q(command)} -n {q(condition)} {spec}')
        return '\n'.join(lines) + '\n'
    lines = [identifier + '() {', '  local context="" candidates="" previous word i']
    if shell == 'bash':
        lines += ['  local current="${COMP_WORDS[COMP_CWORD]}"', '  previous="${COMP_WORDS[COMP_CWORD-1]}"', '  for ((i=1; i<COMP_CWORD; i++)); do', '    word="${COMP_WORDS[i]}"']
    else:
        lines += ['  previous="${words[CURRENT-1]}"', '  for ((i=2; i<CURRENT; i++)); do', '    word="${words[i]}"']
    lines += ['    case "$context|$word" in']
    for pattern, target in transitions:
        lines.append('      ' + q(pattern) + ') context=' + q(target) + ' ;;')
    lines += ['    esac', '  done', '  case "$context|$previous" in']
    for pattern, choices in values.items():
        lines.append('    ' + q(pattern) + ') candidates=' + q(' '.join(choices)) + ' ;;')
    lines += ['    *)', '      case "$context" in']
    for context, choices in contexts.items():
        lines.append('        ' + q(context) + ') candidates=' + q(' '.join(choices)) + ' ;;')
    lines += ['      esac ;;', '  esac']
    if shell == 'bash':
        lines += ['  COMPREPLY=()', '  while IFS= read -r word; do COMPREPLY+=("$word"); done < <(compgen -W "$candidates" -- "$current")', '}', f'complete -o default -F {identifier} {q(command)}']
    else:
        lines += ['  compadd -- ${=candidates} || _files', '}', f'compdef {identifier} {q(command)}']
    return '\n'.join(lines) + '\n'
