"""Rule parsing for ignore files."""

from dataclasses import dataclass

from ignorewhy.globs import (
    DOUBLE_STAR,
    PatternError,
    compile_segment,
    match_path,
    match_segment,
)

EMPTY_SEGMENT = "invalid pattern: empty path segment"


@dataclass(frozen=True)
class Rule:
    line: int
    text: str
    negated: bool
    error: str | None
    dir_only: bool
    anchored: bool
    segments: tuple

    def matches(self, parts, is_dir):
        if self.error is not None:
            return False
        if self.dir_only and not is_dir:
            return False
        if self.anchored:
            return match_path(self.segments, parts)
        if not self.segments or not parts:
            return False
        segment = self.segments[0]
        if isinstance(segment, str) and segment == DOUBLE_STAR:
            return True
        return match_segment(segment, parts[-1])


def split_body(text):
    """Return (negated, dir_only, anchored, raw_segments) or None for an empty body."""
    negated = text.startswith("!")
    body = text[1:] if negated else text
    dir_only = body.endswith("/")
    if dir_only:
        body = body[:-1]
    if not body:
        return None
    anchored = "/" in body
    body = body.removeprefix("/")
    return negated, dir_only, anchored, body.split("/")


def _strip_trailing_spaces(line):
    size = len(line)
    i = 0
    keep = 0
    while i < size:
        if line[i] == "\\":
            i += 2
            keep = min(i, size)
        elif line[i] == " ":
            i += 1
        else:
            i += 1
            keep = i
    return line[:keep]


def _compile(raw_segments):
    """Return (segments, error)."""
    compiled = []
    for raw in raw_segments:
        if raw == "":
            return (), EMPTY_SEGMENT
        if raw == DOUBLE_STAR:
            compiled.append(DOUBLE_STAR)
            continue
        try:
            compiled.append(compile_segment(raw))
        except PatternError as exc:
            return (), str(exc)
    return tuple(compiled), None


def parse_text(text):
    """Parse ignore-file text into a list of rules."""
    text = text.removeprefix("\ufeff")
    rules = []
    for number, line in enumerate(text.split("\n"), start=1):
        line = line.removesuffix("\r")
        line = _strip_trailing_spaces(line)
        if not line or line.startswith("#"):
            continue
        split = split_body(line)
        if split is None:
            continue
        negated, dir_only, anchored, raw_segments = split
        segments, error = _compile(raw_segments)
        rules.append(Rule(number, line, negated, error, dir_only, anchored, segments))
    return rules
