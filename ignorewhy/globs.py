"""Glob segments and path matching for .gitignore rules."""

DOUBLE_STAR = "**"

_LIT = "lit"
_ANY = "any"
_STAR = "star"
_CLASS = "class"

_UNTERMINATED = 'invalid pattern: unterminated "[" class'
_TRAILING = "invalid pattern: trailing backslash"


class PatternError(ValueError):
    """Raised for an invalid glob pattern; the message is the report text."""


def _read_class(text, start):
    """Parse a class whose '[' is at start; return (item, index after ']')."""
    n = len(text)
    j = start + 1
    negated = False
    if j < n and text[j] in "!^":
        negated = True
        j += 1
    ranges = []
    first = True
    while True:
        if j >= n:
            raise PatternError(_UNTERMINATED)
        char = text[j]
        if char == "]" and not first:
            j += 1
            break
        first = False
        if char == "\\":
            if j + 1 >= n:
                raise PatternError(_UNTERMINATED)
            char = text[j + 1]
            j += 2
        else:
            j += 1
        low = char
        high = char
        if j + 1 < n and text[j] == "-" and text[j + 1] != "]":
            if text[j + 1] == "\\":
                if j + 2 >= n:
                    raise PatternError(_UNTERMINATED)
                high = text[j + 2]
                j += 3
            else:
                high = text[j + 1]
                j += 2
        ranges.append((low, high))
    return (_CLASS, negated, tuple(ranges)), j


def compile_segment(text):
    """Compile one glob segment into an immutable tuple of items."""
    items = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char == "\\":
            if i + 1 >= n:
                raise PatternError(_TRAILING)
            items.append((_LIT, text[i + 1]))
            i += 2
        elif char == "*":
            if not items or items[-1][0] != _STAR:
                items.append((_STAR,))
            i += 1
        elif char == "?":
            items.append((_ANY,))
            i += 1
        elif char == "[":
            item, i = _read_class(text, i)
            items.append(item)
        else:
            items.append((_LIT, char))
            i += 1
    return tuple(items)


def _single_matches(item, char):
    kind = item[0]
    if kind == _LIT:
        return item[1] == char
    if kind == _ANY:
        return True
    found = any(low <= char <= high for low, high in item[2])
    return found != item[1]


def match_segment(items, text):
    """Return True when the whole text matches the compiled items."""
    n = len(items)
    size = len(text)
    i = 0
    j = 0
    star = -1
    mark = 0
    while j < size:
        if i < n and items[i][0] == _STAR:
            star = i
            mark = j
            i += 1
        elif i < n and _single_matches(items[i], text[j]):
            i += 1
            j += 1
        elif star != -1:
            i = star + 1
            mark += 1
            j = mark
        else:
            return False
    while i < n and items[i][0] == _STAR:
        i += 1
    return i == n


def match_path(segments, parts):
    """Match path components against segments (DOUBLE_STAR or compiled)."""
    count = len(parts)
    total = len(segments)
    cur = [False] * (count + 1)
    cur[0] = True
    for index, segment in enumerate(segments):
        new = [False] * (count + 1)
        if isinstance(segment, str) and segment == DOUBLE_STAR:
            last = index == total - 1
            for j in range(count + 1):
                if last:
                    new[j] = j > 0 and (cur[j - 1] or new[j - 1])
                else:
                    new[j] = cur[j] or (j > 0 and new[j - 1])
        else:
            for j in range(count):
                if cur[j] and match_segment(segment, parts[j]):
                    new[j + 1] = True
        cur = new
    return cur[count]
