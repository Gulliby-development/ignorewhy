"""Lint ignore-file text for rules that cannot work."""

from ignorewhy.rules import parse_text, split_body
from ignorewhy.ruleset import Layer, decide

_NOT_LITERAL = "*?[\\"
_SPECIAL_ESCAPES = " !#*-?[]^\\"


def _has_partial_double_star(segment):
    """True when an unescaped `**` sits in a segment together with other characters."""
    if segment == "**":
        return False
    i = 0
    while i < len(segment):
        char = segment[i]
        if char == "\\":
            i += 2
            continue
        if char == "*" and segment[i + 1 : i + 2] == "*":
            return True
        i += 1
    return False


def _has_space_before_hash(text):
    """True when an unescaped space is immediately followed by #."""
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == " " and text[i + 1 : i + 2] == "#":
            return True
        i += 1
    return False


def _plain_escape(text):
    i = 0
    while i < len(text):
        if text[i] == "\\":
            if i + 1 < len(text):
                char = text[i + 1]
                if char not in _SPECIAL_ESCAPES:
                    return char
            i += 2
        else:
            i += 1
    return None


def _is_literal(segments):
    return all(not any(c in _NOT_LITERAL for c in segment) for segment in segments)


def _reinclude_problem(segments, earlier):
    layer = Layer("", (), tuple(earlier))
    for size in range(1, len(segments)):
        parent = tuple(segments[:size])
        decision = decide([layer], parent, True)
        if decision.ignored:
            return (
                f'cannot re-include "{"/".join(segments)}": parent directory '
                f'"{"/".join(parent)}" is excluded by line {decision.rule.line}'
            )
    return None


def lint_text(text):
    """Return a sorted list of (line, code, message) problems."""
    problems = []
    earlier = []
    first_seen = {}
    for rule in parse_text(text):
        if rule.error is not None:
            problems.append((rule.line, "IW001", rule.error))
            continue
        if _has_space_before_hash(rule.text):
            problems.append(
                (rule.line, "IW006", '"#" after a space is part of the pattern, not a comment')
            )
        plain = _plain_escape(rule.text)
        if plain is not None:
            problems.append(
                (
                    rule.line,
                    "IW007",
                    f'"\\{plain}" is the same as "{plain}"; use "/" between segments',
                )
            )
        if rule.text in first_seen:
            problems.append((rule.line, "IW002", f"duplicate of line {first_seen[rule.text]}"))
        else:
            first_seen[rule.text] = rule.line
        negated, _dir_only, anchored, segments = split_body(rule.text)
        if negated and anchored and len(segments) >= 2 and _is_literal(segments):
            message = _reinclude_problem(segments, earlier)
            if message is not None:
                problems.append((rule.line, "IW003", message))
        if any(_has_partial_double_star(segment) for segment in segments):
            problems.append((rule.line, "IW004", '"**" only works as a whole path segment'))
        body = rule.text.removeprefix("!")
        for prefix in ("./", "../"):
            if body.startswith(prefix):
                problems.append(
                    (rule.line, "IW005", f'pattern starts with "{prefix}" and never matches')
                )
                break
        earlier.append(rule)
    problems.sort(key=lambda item: (item[0], item[1]))
    return problems
