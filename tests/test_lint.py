"""Tests for lint_text and the lint command."""

import pytest

from ignorewhy.cli import run
from ignorewhy.lint import lint_text

BACKSLASH = "\\"

WORKED_LINES = [
    "/a/",
    "!/a/b/keep.txt",
    "a**b",
    "./foo",
    "foo[",
    "bar" + BACKSLASH,
    "/a/",
    "# done",
]

WORKED_OUTPUT = (
    'ignore.txt:2: IW003 cannot re-include "a/b/keep.txt": parent directory "a" is excluded '
    "by line 1\n"
    'ignore.txt:3: IW004 "**" only works as a whole path segment\n'
    'ignore.txt:4: IW005 pattern starts with "./" and never matches\n'
    'ignore.txt:5: IW001 invalid pattern: unterminated "[" class\n'
    "ignore.txt:6: IW001 invalid pattern: trailing backslash\n"
    "ignore.txt:7: IW002 duplicate of line 1\n"
    "6 problems\n"
)


def iw003(path, parent, number):
    return (
        f'cannot re-include "{path}": parent directory "{parent}" '
        f"is excluded by line {number}"
    )


def run_cli(args, stdin=b""):
    out = []
    err = []
    code = run(args, lambda: stdin, out.append, err.append)
    return code, "".join(out), "".join(err)


def write(path, text):
    path.write_bytes(text.encode("utf-8"))


# ---- lint_text ----


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("foo[", [(1, "IW001", 'invalid pattern: unterminated "[" class')]),
        ("bar" + BACKSLASH, [(1, "IW001", "invalid pattern: trailing backslash")]),
        ("a//b", [(1, "IW001", "invalid pattern: empty path segment")]),
        ("!a//b", [(1, "IW001", "invalid pattern: empty path segment")]),
    ],
)
def test_iw001_messages(text, expected):
    assert lint_text(text) == expected


def test_invalid_rule_gets_only_iw001():
    assert lint_text("./a//b**c") == [(1, "IW001", "invalid pattern: empty path segment")]


def test_duplicate_names_first_line():
    text = "foo\nbar\nfoo\nfoo\n"
    assert lint_text(text) == [
        (3, "IW002", "duplicate of line 1"),
        (4, "IW002", "duplicate of line 1"),
    ]


def test_negated_rule_is_not_duplicate_of_plain_rule():
    assert lint_text("foo\n!foo\n") == []


def test_duplicate_invalid_rules_only_iw001():
    result = lint_text("foo[\nfoo[\n")
    assert [code for _line, code, _message in result] == ["IW001", "IW001"]


def test_iw003_names_shortest_parent_and_line():
    text = "/a/\n!/a/b/keep.txt\n"
    assert lint_text(text) == [(2, "IW003", iw003("a/b/keep.txt", "a", 1))]


def test_iw003_nearer_parent_is_the_ignored_one():
    text = "# c\n/a/b/\n!/a/b/c/d.txt\n"
    assert lint_text(text) == [(3, "IW003", iw003("a/b/c/d.txt", "a/b", 2))]


def test_iw003_prefers_shortest_of_several_ignored_parents():
    text = "/a/\n/a/b/\n!/a/b/c\n"
    assert lint_text(text) == [(3, "IW003", iw003("a/b/c", "a", 1))]


def test_iw003_names_deciding_rule_line():
    text = "/a/\n!/a/\n/a/\n!/a/x\n"
    result = lint_text(text)
    assert (4, "IW003", iw003("a/x", "a", 3)) in result


@pytest.mark.parametrize(
    "text",
    [
        "/a/\n!/a/*/c\n",
        "/a/\n!/a/b?\n",
        "/a/\n!/a/[bc]\n",
        "/a/\n!/a/**/c\n",
        "/a/\n!/a/b" + BACKSLASH + "*\n",
        "/a/\n!/a\n",
        "/a/\n!a\n",
        "/b/\n!/a/b\n",
        "!/a/b\n/a/\n",
        "/a/\n/a/b\n",
    ],
)
def test_no_iw003(text):
    assert [item for item in lint_text(text) if item[1] == "IW003"] == []


def test_iw004_partial_double_star():
    assert lint_text("a**b") == [(1, "IW004", '"**" only works as a whole path segment')]


@pytest.mark.parametrize("text", ["a**", "**b", "x/a**b/y", "!a**b"])
def test_iw004_variants(text):
    assert [code for _line, code, _message in lint_text(text)] == ["IW004"]


@pytest.mark.parametrize(
    "text",
    [
        "a" + BACKSLASH + "**b",
        "a" + BACKSLASH + "*" + BACKSLASH + "*b",
        "a" + BACKSLASH + "**",
        "**",
        "**/x",
        "x/**",
        "a/**/b",
        "a*b",
    ],
)
def test_no_iw004(text):
    assert [item for item in lint_text(text) if item[1] == "IW004"] == []


@pytest.mark.parametrize(
    ("text", "prefix"),
    [
        ("./foo", "./"),
        ("../x", "../"),
        ("!./x", "./"),
        ("!../x", "../"),
    ],
)
def test_iw005(text, prefix):
    expected = [(1, "IW005", f'pattern starts with "{prefix}" and never matches')]
    assert lint_text(text) == expected


@pytest.mark.parametrize("text", ["foo/./x", "x/../y", ".foo", "..x", "/./x"])
def test_no_iw005(text):
    assert [item for item in lint_text(text) if item[1] == "IW005"] == []


def test_several_problems_on_one_line_ordered_by_code():
    assert lint_text("./a**b") == [
        (1, "IW004", '"**" only works as a whole path segment'),
        (1, "IW005", 'pattern starts with "./" and never matches'),
    ]


def test_duplicate_and_iw005_on_one_line_ordered_by_code():
    assert lint_text("./x\n./x\n") == [
        (1, "IW005", 'pattern starts with "./" and never matches'),
        (2, "IW002", "duplicate of line 1"),
        (2, "IW005", 'pattern starts with "./" and never matches'),
    ]


def test_results_in_line_order():
    result = lint_text("./x\nfoo\nfoo[\n")
    assert [line for line, _code, _message in result] == [1, 3]


@pytest.mark.parametrize(
    "text", ["", "\n", "# only a comment\n", "foo\n*.log\n!keep.log\n/dist\n"]
)
def test_clean_text_gives_empty_list(text):
    assert lint_text(text) == []


# ---- lint command ----


def test_worked_example(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "ignore.txt", "\n".join(WORKED_LINES) + "\n")
    code, out, err = run_cli(["lint", "ignore.txt"])
    assert (code, out, err) == (1, WORKED_OUTPUT, "")
    assert len(out.splitlines()) == 7


@pytest.mark.parametrize(
    ("content", "summary"),
    [
        ("foo\n", "ok, 1 rule in 1 file\n"),
        ("foo\nbar\n", "ok, 2 rules in 1 file\n"),
        ("# nothing\n\n", "ok, 0 rules in 1 file\n"),
    ],
)
def test_clean_single_file(tmp_path, monkeypatch, content, summary):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "f.txt", content)
    assert run_cli(["lint", "f.txt"]) == (0, summary, "")


def test_clean_several_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "a.txt", "foo\nbar\n")
    write(tmp_path / "b.txt", "baz\n")
    assert run_cli(["lint", "a.txt", "b.txt"]) == (0, "ok, 3 rules in 2 files\n", "")


def test_single_problem_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "f.txt", "foo\nfoo\n")
    code, out, err = run_cli(["lint", "f.txt"])
    assert (code, out, err) == (1, "f.txt:2: IW002 duplicate of line 1\n1 problem\n", "")


def test_several_files_in_file_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "a.txt", "foo[\n")
    write(tmp_path / "b.txt", "./x\n")
    expected = (
        'b.txt:1: IW005 pattern starts with "./" and never matches\n'
        'a.txt:1: IW001 invalid pattern: unterminated "[" class\n'
        "2 problems\n"
    )
    assert run_cli(["lint", "b.txt", "a.txt"]) == (1, expected, "")


def test_gitignore_next_to_file_does_not_change_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "rules.txt", "foo\n!bar\n")
    before = run_cli(["lint", "rules.txt"])
    write(tmp_path / ".gitignore", "*.txt\nrules.txt\n/a/\n")
    after = run_cli(["lint", "rules.txt"])
    assert before == after == (0, "ok, 2 rules in 1 file\n", "")


def test_lint_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_cli(["lint"]) == (2, "", "ignorewhy: missing FILE\n")


def test_lint_unreadable_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_cli(["lint", "missing.txt"]) == (
        2,
        "",
        "ignorewhy: missing.txt: cannot read the file\n",
    )


def test_lint_unreadable_file_backslash_shown_as_slash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_cli(["lint", "no" + BACKSLASH + "file.txt"]) == (
        2,
        "",
        "ignorewhy: no/file.txt: cannot read the file\n",
    )


def test_lint_non_utf8_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.txt").write_bytes(b"foo\n\xff\xfe\n")
    assert run_cli(["lint", "bad.txt"]) == (
        2,
        "",
        "ignorewhy: bad.txt: input is not valid UTF-8\n",
    )


def test_error_after_good_file_keeps_stdout_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "good.txt", "foo[\n")
    code, out, err = run_cli(["lint", "good.txt", "missing.txt"])
    assert (code, out) == (2, "")
    assert err == "ignorewhy: missing.txt: cannot read the file\n"


def test_lint_rejects_options(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "f.txt", "foo\n")
    assert run_cli(["lint", "--root", "d", "f.txt"]) == (
        2,
        "",
        'ignorewhy: unknown option "--root"\n',
    )
