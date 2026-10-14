"""Tests for layers, decisions and the loader."""

import pytest

from ignorewhy.errors import UsageError
from ignorewhy.loader import LayerSource, decode, display_name, load_exclude
from ignorewhy.rules import parse_text
from ignorewhy.ruleset import Decision, Layer, decide


def make_layer(label, base, text):
    return Layer(label, tuple(base), tuple(parse_text(text)))


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def parts_of(text):
    return tuple(text.split("/"))


# ---- decisions with in-memory layers ----


def test_no_match_is_not_ignored_without_layer_or_rule():
    result = decide([make_layer(".gitignore", (), "*.log\n")], ("a.txt",), False)
    assert result == Decision(False, None, None, None)


def test_no_layers_at_all():
    result = decide([], ("a", "b"), False)
    assert result.ignored is False
    assert result.layer is None
    assert result.rule is None
    assert result.via is None


def test_simple_match_is_ignored():
    layer = make_layer(".gitignore", (), "*.log\n")
    result = decide([layer], ("a.log",), False)
    assert result.ignored is True
    assert result.layer is layer
    assert result.rule.line == 1
    assert result.via is None


def test_last_rule_in_layer_wins_negation_after():
    layer = make_layer(".gitignore", (), "*.log\n!keep.log\n")
    result = decide([layer], ("keep.log",), False)
    assert result.ignored is False
    assert result.rule.line == 2
    assert result.rule.negated is True
    assert result.layer is layer


def test_last_rule_in_layer_wins_ignore_after():
    layer = make_layer(".gitignore", (), "!keep.log\n*.log\n")
    result = decide([layer], ("keep.log",), False)
    assert result.ignored is True
    assert result.rule.line == 2


def test_negated_rule_alone_gives_not_ignored_with_rule():
    layer = make_layer(".gitignore", (), "!a.txt\n")
    result = decide([layer], ("a.txt",), False)
    assert result.ignored is False
    assert result.rule.text == "!a.txt"
    assert result.layer is layer


def test_deepest_layer_wins_over_shallower():
    root = make_layer(".gitignore", (), "*.tmp\n")
    docs = make_layer("docs/.gitignore", ("docs",), "!*.tmp\n")
    result = decide([root, docs], ("docs", "x.tmp"), False)
    assert result.ignored is False
    assert result.layer is docs
    assert result.rule.line == 1


def test_deeper_layer_without_match_falls_back_to_shallower():
    root = make_layer(".gitignore", (), "*.tmp\n")
    docs = make_layer("docs/.gitignore", ("docs",), "*.log\n")
    result = decide([root, docs], ("docs", "x.tmp"), False)
    assert result.ignored is True
    assert result.layer is root


def test_layer_does_not_apply_outside_its_folder():
    docs = make_layer("docs/.gitignore", ("docs",), "*.tmp\n")
    assert decide([docs], ("other", "x.tmp"), False).ignored is False
    assert decide([docs], ("x.tmp",), False).ignored is False
    assert decide([docs], ("docs2", "x.tmp"), False).ignored is False


def test_layer_does_not_apply_to_its_own_base_directory():
    docs = make_layer("docs/.gitignore", ("docs",), "*\n")
    result = decide([docs], ("docs",), True)
    assert result == Decision(False, None, None, None)


def test_layer_applies_to_a_path_below_its_base():
    docs = make_layer("docs/.gitignore", ("docs",), "*.tmp\n")
    assert decide([docs], ("docs", "a", "x.tmp"), False).ignored is True


def test_rule_sees_the_path_without_the_base():
    anchored = make_layer("docs/.gitignore", ("docs",), "/notes.tmp\n")
    assert decide([anchored], ("docs", "notes.tmp"), False).ignored is True
    assert decide([anchored], ("docs", "sub", "notes.tmp"), False).ignored is False


def test_anchored_negation_in_deeper_layer_overrides_root():
    root = make_layer(".gitignore", (), "*.tmp\n")
    docs = make_layer("docs/.gitignore", ("docs",), "*.tmp\n!/notes.tmp\n")
    result = decide([root, docs], ("docs", "notes.tmp"), False)
    assert result.ignored is False
    assert result.rule.line == 2
    assert result.layer is docs


def test_exclude_layer_is_weakest():
    exclude = make_layer("ex.txt", (), "*.o\n")
    root = make_layer(".gitignore", (), "!*.o\n")
    result = decide([exclude, root], ("a.o",), False)
    assert result.ignored is False
    assert result.layer is root


def test_exclude_layer_decides_when_alone():
    exclude = make_layer("ex.txt", (), "*.o\n")
    root = make_layer(".gitignore", (), "*.log\n")
    result = decide([exclude, root], ("tmp", "x.o"), False)
    assert result.ignored is True
    assert result.layer is exclude
    assert result.rule.line == 1


def test_directory_only_rule_needs_a_directory():
    layer = make_layer(".gitignore", (), "build/\n")
    assert decide([layer], ("build",), True).ignored is True
    assert decide([layer], ("build",), False).ignored is False


def test_directory_itself_has_no_via():
    layer = make_layer(".gitignore", (), "build/\n")
    result = decide([layer], ("build",), True)
    assert result.ignored is True
    assert result.via is None


# ---- ancestor directories ----


@pytest.mark.parametrize("path", ["build/keep.txt", "build/a/b.txt"])
def test_reinclude_below_ignored_directory_fails(path):
    layer = make_layer(".gitignore", (), "build/\n!build/keep.txt\n")
    result = decide([layer], parts_of(path), False)
    assert result.ignored is True
    assert result.via == "build/"
    assert result.rule.line == 1
    assert result.layer is layer


def test_reinclude_works_after_dir_star():
    layer = make_layer(".gitignore", (), "dir/*\n!dir/keep.txt\n")
    kept = decide([layer], ("dir", "keep.txt"), False)
    assert kept.ignored is False
    assert kept.rule.line == 2
    assert kept.via is None
    other = decide([layer], ("dir", "other.txt"), False)
    assert other.ignored is True
    assert other.rule.line == 1
    assert other.via is None


def test_shortest_ignored_ancestor_is_via():
    layer = make_layer(".gitignore", (), "a/\na/b/\n")
    result = decide([layer], ("a", "b", "c.txt"), False)
    assert result.via == "a/"
    assert result.rule.line == 1


def test_ancestor_is_decided_as_directory_not_file():
    layer = make_layer(".gitignore", (), "build\n")
    result = decide([layer], ("build", "x.txt"), False)
    assert result.ignored is True
    assert result.via == "build/"


def test_non_ignored_ancestor_does_not_hide_own_decision():
    layer = make_layer(".gitignore", (), "*.txt\n")
    result = decide([layer], ("src", "a.txt"), False)
    assert result.ignored is True
    assert result.via is None


def test_ancestor_reincluded_by_negation_is_not_ignored():
    layer = make_layer(".gitignore", (), "build/\n!build/\n")
    result = decide([layer], ("build", "x.txt"), False)
    assert result.ignored is False
    assert result.via is None


def test_decide_accepts_a_list_of_parts():
    layer = make_layer(".gitignore", (), "build/\n")
    assert decide([layer], ["build", "x"], False).via == "build/"


# ---- loader ----


def test_layers_order_and_labels(tmp_path):
    put(tmp_path / "ex.txt", "*.o\n")
    put(tmp_path / ".gitignore", "build/\n")
    put(tmp_path / "docs" / ".gitignore", "*.tmp\n")
    exclude = load_exclude(str(tmp_path / "ex.txt"))
    source = LayerSource(tmp_path, exclude)
    layers = source.layers_for(("docs", "sub", "x.tmp"))
    assert [layer.base for layer in layers] == [(), (), ("docs",)]
    assert layers[0] is exclude
    assert layers[1].label == ".gitignore"
    assert layers[2].label == "docs/.gitignore"
    assert layers[1].rules[0].text == "build/"
    assert layers[2].rules[0].text == "*.tmp"


def test_layers_without_exclude(tmp_path):
    put(tmp_path / ".gitignore", "a\n")
    layers = LayerSource(tmp_path, None).layers_for(("x",))
    assert [layer.label for layer in layers] == [".gitignore"]


def test_deep_labels_use_slash(tmp_path):
    put(tmp_path / "a" / "b" / ".gitignore", "x\n")
    layers = LayerSource(tmp_path, None).layers_for(("a", "b", "c", "f"))
    assert [layer.label for layer in layers] == ["a/b/.gitignore"]
    assert layers[0].base == ("a", "b")


def test_missing_gitignore_gives_no_layer(tmp_path):
    (tmp_path / "src").mkdir()
    put(tmp_path / ".gitignore", "a\n")
    layers = LayerSource(tmp_path, None).layers_for(("src", "x.py"))
    assert [layer.label for layer in layers] == [".gitignore"]


def test_directory_named_gitignore_gives_no_layer(tmp_path):
    (tmp_path / "other" / ".gitignore").mkdir(parents=True)
    (tmp_path / ".gitignore").mkdir()
    source = LayerSource(tmp_path, None)
    assert source.layers_for(("other", "x.txt")) == []


def test_layer_of_the_path_itself_is_not_loaded(tmp_path):
    put(tmp_path / "docs" / ".gitignore", "*.tmp\n")
    assert LayerSource(tmp_path, None).layers_for(("docs",)) == []


def test_layers_are_cached_per_run(tmp_path):
    put(tmp_path / ".gitignore", "a\n")
    source = LayerSource(tmp_path, None)
    first = source.layers_for(("x",))
    (tmp_path / ".gitignore").unlink()
    assert source.layers_for(("y",))[0] is first[0]


def test_gitignore_with_bom_and_crlf(tmp_path):
    (tmp_path / ".gitignore").write_bytes(b"\xef\xbb\xbf# c\r\nfoo\r\n\r\nbar \r\n")
    layer = LayerSource(tmp_path, None).layers_for(("x",))[0]
    assert [(rule.line, rule.text) for rule in layer.rules] == [(2, "foo"), (4, "bar")]


def test_non_utf8_gitignore_raises(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".gitignore").write_bytes(b"\xff\xfe\n")
    with pytest.raises(UsageError) as info:
        LayerSource(tmp_path, None).layers_for(("docs", "x"))
    assert str(info.value) == "docs/.gitignore: input is not valid UTF-8"


def test_load_exclude_label_is_the_argument(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    put(tmp_path / "ex.txt", "*.o\n")
    layer = load_exclude("ex.txt")
    assert layer.label == "ex.txt"
    assert layer.base == ()
    assert layer.rules[0].text == "*.o"


def test_load_exclude_unreadable_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(UsageError) as info:
        load_exclude("missing.txt")
    assert str(info.value) == "missing.txt: cannot read the file"


def test_load_exclude_label_shows_backslash_as_slash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(UsageError) as info:
        load_exclude("no\\such.txt")
    assert str(info.value) == "no/such.txt: cannot read the file"


def test_load_exclude_directory_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "adir").mkdir()
    with pytest.raises(UsageError) as info:
        load_exclude("adir")
    assert str(info.value) == "adir: cannot read the file"


def test_load_exclude_non_utf8(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.txt").write_bytes(b"\xc3\x28\n")
    with pytest.raises(UsageError) as info:
        load_exclude("bad.txt")
    assert str(info.value) == "bad.txt: input is not valid UTF-8"


def test_display_name_and_decode():
    assert display_name("a\\b\\c.txt") == "a/b/c.txt"
    assert display_name("plain") == "plain"
    assert decode("\u00e9".encode(), "x") == "\u00e9"
    with pytest.raises(UsageError) as info:
        decode(b"\xff", "<stdin>")
    assert str(info.value) == "<stdin>: input is not valid UTF-8"


# ---- loader and decide together ----


def build_example(tmp_path):
    put(tmp_path / ".gitignore", "build/\n*.log\n!keep.log\n/dist\n")
    put(tmp_path / "docs" / ".gitignore", "*.tmp\n!/notes.tmp\n")
    return LayerSource(tmp_path, None)


@pytest.mark.parametrize(
    ("path", "is_dir", "ignored", "label", "line", "via"),
    [
        ("build/app.js", False, True, ".gitignore", 1, "build/"),
        ("build", True, True, ".gitignore", 1, None),
        ("a.log", False, True, ".gitignore", 2, None),
        ("keep.log", False, False, ".gitignore", 3, None),
        ("dist", False, True, ".gitignore", 4, None),
        ("src/dist/x.txt", False, False, None, None, None),
        ("docs/x.tmp", False, True, "docs/.gitignore", 1, None),
        ("docs/notes.tmp", False, False, "docs/.gitignore", 2, None),
        ("README.md", False, False, None, None, None),
    ],
)
def test_worked_example_decisions(tmp_path, path, is_dir, ignored, label, line, via):
    source = build_example(tmp_path)
    parts = parts_of(path)
    result = decide(source.layers_for(parts), parts, is_dir)
    assert result.ignored is ignored
    assert result.via == via
    if label is None:
        assert result.layer is None
        assert result.rule is None
    else:
        assert result.layer.label == label
        assert result.rule.line == line


def test_exclude_loses_against_root_gitignore_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    put(tmp_path / "ex.txt", "*.o\n")
    put(tmp_path / ".gitignore", "!keep.o\n")
    source = LayerSource(tmp_path, load_exclude("ex.txt"))
    kept = decide(source.layers_for(("keep.o",)), ("keep.o",), False)
    assert kept.ignored is False
    assert kept.layer.label == ".gitignore"
    other = decide(source.layers_for(("tmp", "x.o")), ("tmp", "x.o"), False)
    assert other.ignored is True
    assert other.layer.label == "ex.txt"
