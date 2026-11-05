"""Tests of the filter option --count."""

import pytest

from ignorewhy.cli import run

PATHS = b"src/main.py\nbuild/x.o\n.cache/\nlogs/a.log\nsrc/\n"


def invoke(args, stdin=b""):
    out = []
    err = []
    code = run(args, lambda: stdin, out.append, err.append)
    return code, "".join(out), err


@pytest.fixture
def ex(tmp_path):
    root = tmp_path / "ex"
    (root / "docs").mkdir(parents=True)
    (root / ".gitignore").write_bytes(b"build/\n*.log\n!keep.log\n/dist\n")
    (root / "docs" / ".gitignore").write_bytes(b"*.tmp\n!/notes.tmp\n")
    return root


def test_count_prints_the_number_of_paths_that_are_not_ignored(ex):
    assert invoke(["filter", "--root", str(ex), "--count"], PATHS) == (0, "3\n", [])


def test_count_with_ignored_prints_the_number_of_ignored_paths(ex):
    assert invoke(["filter", "--root", str(ex), "--ignored", "--count"], PATHS) == (0, "2\n", [])


def test_count_may_come_before_or_after_the_other_options_and_the_file(ex, tmp_path):
    (tmp_path / "paths.txt").write_bytes(PATHS)
    path = str(tmp_path / "paths.txt")
    for args in (
        ["filter", "--count", "--root", str(ex), path],
        ["filter", path, "--root", str(ex), "--count"],
        ["filter", "--root", str(ex), "--count", "--count", path],
    ):
        assert invoke(args, b"ignored") == (0, "3\n", [])


def test_count_reads_standard_input_with_a_dash(ex):
    assert invoke(["filter", "--root", str(ex), "--count", "-"], PATHS) == (0, "3\n", [])


def test_count_is_zero_when_no_path_is_printed(ex):
    assert invoke(["filter", "--root", str(ex), "--count"], b"build/\nx.log\n") == (0, "0\n", [])
    assert invoke(["filter", "--root", str(ex), "--count"], b"") == (0, "0\n", [])
    assert invoke(["filter", "--root", str(ex), "--ignored", "--count"], b"src/a.py\n") == (
        0,
        "0\n",
        [],
    )


def test_count_skips_empty_lines_and_reads_bom_and_crlf(ex):
    data = b"\xef\xbb\xbfsrc/main.py\r\n\r\nbuild/x.o\r\n\nlogs/a.log\r\nsrc/\r\n"
    assert invoke(["filter", "--root", str(ex), "--count"], data) == (0, "2\n", [])


def test_count_counts_every_line_even_when_paths_repeat(ex):
    assert invoke(["filter", "--root", str(ex), "--count"], b"a.py\na.py\na.py\n") == (0, "3\n", [])


def test_count_without_the_option_prints_the_paths(ex):
    assert invoke(["filter", "--root", str(ex)], b"a.py\nb.log\n") == (0, "a.py\n", [])


@pytest.mark.parametrize("command", ["explain", "lint"])
def test_count_belongs_to_filter_only(command):
    code, out, err = invoke([command, "--count", "x"])
    assert (code, out) == (2, "")
    assert err == ['ignorewhy: unknown option "--count"\n']


def test_count_takes_no_value(ex):
    code, out, err = invoke(["filter", "--root", str(ex), "--count=1"], PATHS)
    assert (code, out) == (2, "")
    assert err == ['ignorewhy: unknown option "--count=1"\n']
