"""Reading ignore files and building the layers of a path."""

from ignorewhy.errors import UsageError
from ignorewhy.rules import parse_text
from ignorewhy.ruleset import Layer


def display_name(arg):
    """Show an argument with every backslash as a slash."""
    return arg.replace("\\", "/")


def decode(data, label):
    """Decode bytes as strict UTF-8 or raise the file error for label."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UsageError(f"{label}: input is not valid UTF-8") from None


def read_file(path, label):
    """Read a file as bytes and decode it."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        raise UsageError(f"{label}: cannot read the file") from None
    return decode(data, label)


def load_exclude(arg):
    """Load the --exclude file, named as written, as a layer with an empty base."""
    label = display_name(arg)
    rules = tuple(parse_text(read_file(arg, label)))
    return Layer(label, (), rules)


class LayerSource:
    """Builds the layers of a path from the exclude layer and .gitignore files."""

    def __init__(self, root, exclude):
        self.root = root
        self.exclude = exclude
        self._cache = {}

    def _layer_at(self, base):
        if base not in self._cache:
            self._cache[base] = self._load(base)
        return self._cache[base]

    def _load(self, base):
        path = self.root.joinpath(*base, ".gitignore")
        if not path.is_file():
            return None
        label = "/".join((*base, ".gitignore"))
        rules = tuple(parse_text(read_file(path, label)))
        return Layer(label, base, rules)

    def layers_for(self, parts):
        """Return the layers for a path, weakest first."""
        layers = []
        if self.exclude is not None:
            layers.append(self.exclude)
        for size in range(len(parts)):
            layer = self._layer_at(tuple(parts[:size]))
            if layer is not None:
                layers.append(layer)
        return layers
