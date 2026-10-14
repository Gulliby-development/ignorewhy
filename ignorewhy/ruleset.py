"""Layers and the decision of one path."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Layer:
    label: str
    base: tuple
    rules: tuple


@dataclass(frozen=True)
class Decision:
    ignored: bool
    layer: Layer | None
    rule: object
    via: str | None


def _own_decision(layers, parts, is_dir):
    """Decide one path by the layers alone, strongest layer first."""
    for layer in reversed(layers):
        size = len(layer.base)
        if size >= len(parts) or tuple(parts[:size]) != tuple(layer.base):
            continue
        relative = tuple(parts[size:])
        for rule in reversed(layer.rules):
            if rule.matches(relative, is_dir):
                return Decision(not rule.negated, layer, rule, None)
    return Decision(False, None, None, None)


def decide(layers, parts, is_dir):
    """Decide whether the path is ignored, checking ancestor directories first."""
    parts = tuple(parts)
    for size in range(1, len(parts)):
        ancestor = parts[:size]
        found = _own_decision(layers, ancestor, True)
        if found.ignored:
            return Decision(True, found.layer, found.rule, "/".join(ancestor) + "/")
    return _own_decision(layers, parts, is_dir)
