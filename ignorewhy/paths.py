"""Normalization of PATH arguments."""

from ignorewhy.errors import UsageError


def normalize(arg):
    """Return (parts, is_dir) for a PATH argument; raise UsageError if invalid."""
    error = UsageError(f'invalid path "{arg}"')
    text = arg.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if not text or text.startswith("/"):
        raise error
    if len(text) >= 2 and text[1] == ":" and text[0].isascii() and text[0].isalpha():
        raise error
    is_dir = text.endswith("/")
    if is_dir:
        text = text[:-1]
    parts = tuple(text.split("/"))
    for part in parts:
        if part in ("", ".", ".."):
            raise error
    return parts, is_dir


def display(parts, is_dir):
    """Join parts with `/`, adding a trailing `/` for a directory."""
    text = "/".join(parts)
    return text + "/" if is_dir else text
