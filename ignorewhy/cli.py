"""Command line front end: argument reading and the three commands."""

import sys
from pathlib import Path

from ignorewhy import report
from ignorewhy.errors import UsageError
from ignorewhy.lint import lint_text
from ignorewhy.loader import LayerSource, decode, display_name, load_exclude, read_file
from ignorewhy.paths import display, normalize
from ignorewhy.rules import parse_text
from ignorewhy.ruleset import decide

COMMANDS = ("explain", "filter", "lint")
OPTIONS = ("--root", "--exclude")


def _read_arguments(command, rest):
    """Return (options, positional) reading left to right; the first problem ends it."""
    options = {"--root": ".", "--exclude": None}
    positional = []
    allowed = () if command == "lint" else OPTIONS
    index = 0
    while index < len(rest):
        arg = rest[index]
        index += 1
        if arg in allowed:
            if index >= len(rest):
                raise UsageError(f"{arg} needs a value")
            options[arg] = rest[index]
            index += 1
            continue
        name, equals, value = arg.partition("=")
        if equals and name in allowed:
            options[name] = value
            continue
        if arg.startswith("-") and arg != "-":
            raise UsageError(f'unknown option "{arg}"')
        positional.append(arg)
    return options, positional


def _split_lines(text):
    lines = []
    for line in text.removeprefix("\ufeff").split("\n"):
        line = line.removesuffix("\r")
        if line:
            lines.append(line)
    return lines


def _explain(source, paths):
    parsed = [normalize(arg) for arg in paths]
    lines = []
    any_ignored = False
    for parts, is_dir in parsed:
        decision = decide(source.layers_for(parts), parts, is_dir)
        any_ignored = any_ignored or decision.ignored
        lines.append(report.explain_line(display(parts, is_dir), decision))
    return lines, 0 if any_ignored else 1


def _filter(source, stdin, file_arg):
    if file_arg is None or file_arg == "-":
        text = decode(stdin(), "<stdin>")
    else:
        text = read_file(file_arg, display_name(file_arg))
    entries = [(line, normalize(line)) for line in _split_lines(text)]
    lines = []
    for line, (parts, is_dir) in entries:
        if not decide(source.layers_for(parts), parts, is_dir).ignored:
            lines.append(line)
    return lines, 0


def _lint(files):
    texts = [(display_name(arg), read_file(arg, display_name(arg))) for arg in files]
    lines = []
    problems = 0
    rules = 0
    for label, text in texts:
        rules += len(parse_text(text))
        for line, code, message in lint_text(text):
            lines.append(report.lint_line(label, line, code, message))
            problems += 1
    lines.append(report.lint_summary(problems, rules, len(files)))
    return lines, 1 if problems else 0


def _execute(args, stdin):
    if list(args) == ["--help"]:
        return list(report.USAGE), 0
    if not args:
        raise UsageError("missing command (explain, filter or lint)")
    command = args[0]
    if command not in COMMANDS:
        raise UsageError(f'unknown command "{command}"')
    options, positional = _read_arguments(command, args[1:])
    if command == "explain" and not positional:
        raise UsageError("missing PATH")
    if command == "lint" and not positional:
        raise UsageError("missing FILE")
    if command == "filter" and len(positional) > 1:
        raise UsageError("too many arguments")
    if command == "lint":
        return _lint(positional)
    root = options["--root"]
    if not Path(root).is_dir():
        raise UsageError(f'invalid --root "{root}": not a directory')
    exclude = options["--exclude"]
    layer = load_exclude(exclude) if exclude is not None else None
    source = LayerSource(Path(root), layer)
    if command == "explain":
        return _explain(source, positional)
    return _filter(source, stdin, positional[0] if positional else None)


def run(args, stdin, out, err):
    """Run the command; stdin() returns bytes, out and err take text."""
    try:
        lines, code = _execute(list(args), stdin)
    except UsageError as exc:
        err(report.error_line(str(exc)) + "\n")
        return 2
    if lines:
        out("".join(line + "\n" for line in lines))
    return code


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    return run(argv, sys.stdin.buffer.read, sys.stdout.write, sys.stderr.write)
