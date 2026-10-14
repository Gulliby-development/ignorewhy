"""Tests of the command line: usage, errors, paths, explain, filter, structure and docs."""

import ast
from pathlib import Path

import pytest

from ignorewhy.cli import run
from ignorewhy.errors import UsageError
from ignorewhy.paths import normalize

REPO = Path(__file__).resolve().parent.parent

USAGE_LINES = (
    "usage: ignorewhy explain [--root DIR] [--exclude FILE] PATH...",
    "       ignorewhy filter [--root DIR] [--exclude FILE] [FILE]",
    "       ignorewhy lint FILE...",
)

EXPLAIN_ARGS = [
    "build/app.js", "build/", "a.log", "keep.log", "dist", "src/dist/x.txt",
    "docs/x.tmp", "docs/notes.tmp", "README.md",
]
EXPLAIN_LINES = (
    "build/app.js: ignored (.gitignore:1: build/) via build/",
    "build/: ignored (.gitignore:1: build/)",
    "a.log: ignored (.gitignore:2: *.log)",
    "keep.log: not ignored (.gitignore:3: !keep.log)",
    "dist: ignored (.gitignore:4: /dist)",
    "src/dist/x.txt: not ignored",
    "docs/x.tmp: ignored (docs/.gitignore:1: *.tmp)",
    "docs/notes.tmp: not ignored (docs/.gitignore:2: !/notes.tmp)",
    "README.md: not ignored",
)
LINT_LINES = (
    (
        'ignore.txt:2: IW003 cannot re-include "a/b/keep.txt": parent directory "a" is excluded'
        " by line 1"
    ),
    'ignore.txt:3: IW004 "**" only works as a whole path segment',
    'ignore.txt:4: IW005 pattern starts with "./" and never matches',
    'ignore.txt:5: IW001 invalid pattern: unterminated "[" class',
    "ignore.txt:6: IW001 invalid pattern: trailing backslash",
    "ignore.txt:7: IW002 duplicate of line 1",
    "6 problems",
)
STDIN_PATHS = b"src/main.py\nbuild/x.o\n.cache/\nlogs/a.log\nsrc/\n"
FILTER_OUT = "src/main.py\n.cache/\nsrc/\n"


def invoke(args, stdin=b""):
    out = []
    err = []
    code = run(args, lambda: stdin, out.append, err.append)
    return code, "".join(out), err


def lines_of(*lines):
    return "".join(line + "\n" for line in lines)


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "file.txt").write_bytes(b"x\n")
    (tmp_path / "bad.bin").write_bytes(b"\xff\xfe\x00\xc3\x28\n")
    (tmp_path / "adir").mkdir()
    return tmp_path


@pytest.fixture
def ex(tmp_path):
    root = tmp_path / "ex"
    (root / "docs").mkdir(parents=True)
    (root / ".gitignore").write_bytes(b"build/\n*.log\n!keep.log\n/dist\n")
    (root / "docs" / ".gitignore").write_bytes(b"*.tmp\n!/notes.tmp\n")
    return root


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        result[key] = (path.stat().st_size, path.read_bytes()) if path.is_file() else None
    return result


# --- usage ---------------------------------------------------------------------------------


def test_help_prints_three_lines():
    code, out, err = invoke(["--help"])
    assert code == 0
    assert out == lines_of(*USAGE_LINES)
    assert err == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "missing command (explain, filter or lint)"),
        (["frobnicate"], 'unknown command "frobnicate"'),
        (["--help", "x"], 'unknown command "--help"'),
        (["-x"], 'unknown command "-x"'),
        (["explain", "--help"], 'unknown option "--help"'),
        (["explain", "-x", "a"], 'unknown option "-x"'),
        (["filter", "-q"], 'unknown option "-q"'),
        (["lint", "--root", "d", "f"], 'unknown option "--root"'),
        (["lint", "--exclude=x", "f"], 'unknown option "--exclude=x"'),
        (["explain", "a", "--root"], "--root needs a value"),
        (["explain", "a", "--exclude"], "--exclude needs a value"),
        (["filter", "--exclude"], "--exclude needs a value"),
        (["explain", "-x", "--root"], 'unknown option "-x"'),
        (["explain", "--root", "--bogus"], "missing PATH"),
        (["explain", "a", "--root", "nodir", "-z"], 'unknown option "-z"'),
    ],
)
def test_usage_errors_in_order(work, args, message):
    code, out, err = invoke(args)
    assert code == 2
    assert out == ""
    assert err == [f"ignorewhy: {message}\n"]


# --- errors after reading the arguments ------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "stdin", "message"),
    [
        (["explain"], b"", "missing PATH"),
        (["explain", "--root", "."], b"", "missing PATH"),
        (["lint"], b"", "missing FILE"),
        (["filter", "a", "b"], b"", "too many arguments"),
        (["filter", "--root", "nodir", "a", "b"], b"", "too many arguments"),
        (["explain", "--root", "file.txt", "a"], b"", 'invalid --root "file.txt": not a directory'),
        (["explain", "--root", "nodir", "a"], b"", 'invalid --root "nodir": not a directory'),
        (["filter", "--root=file.txt"], b"", 'invalid --root "file.txt": not a directory'),
        (["explain", "--exclude", "nope.txt", "a"], b"", "nope.txt: cannot read the file"),
        (["explain", "--exclude", "adir", "a"], b"", "adir: cannot read the file"),
        (["explain", "--exclude", "no\\such.txt", "a"], b"", "no/such.txt: cannot read the file"),
        (["explain", "--exclude", "bad.bin", "a"], b"", "bad.bin: input is not valid UTF-8"),
        (["filter", "nope.txt"], b"", "nope.txt: cannot read the file"),
        (["filter", "sub\\nope.txt"], b"", "sub/nope.txt: cannot read the file"),
        (["filter", "bad.bin"], b"", "bad.bin: input is not valid UTF-8"),
        (["filter"], b"\xff\n", "<stdin>: input is not valid UTF-8"),
        (["filter", "-"], b"a\n\xc3\x28\n", "<stdin>: input is not valid UTF-8"),
        (["lint", "nope.txt"], b"", "nope.txt: cannot read the file"),
        (["lint", "x\\nope.txt"], b"", "x/nope.txt: cannot read the file"),
        (["lint", "bad.bin"], b"", "bad.bin: input is not valid UTF-8"),
        (["explain", "a", "../b"], b"", 'invalid path "../b"'),
        (["explain", "ok.txt", "a//b", "c"], b"", 'invalid path "a//b"'),
        (["explain", "--root", "nodir", "../b"], b"", 'invalid --root "nodir": not a directory'),
        (["explain", "--exclude", "nope.txt", "../b"], b"", "nope.txt: cannot read the file"),
        (["filter"], b"a.txt\n../x\n", 'invalid path "../x"'),
        (["filter"], b"a.txt\n/abs\n", 'invalid path "/abs"'),
    ],
)
def test_errors_exit_two_with_one_line(work, args, stdin, message):
    code, out, err = invoke(args, stdin)
    assert code == 2
    assert out == ""
    assert err == [f"ignorewhy: {message}\n"]
    assert err[0].count("\n") == 1
    assert "\r" not in err[0]


def test_explain_error_writes_nothing_after_valid_paths(work):
    code, out, err = invoke(["explain", "a.txt", "b.txt", "c/../d"])
    assert (code, out) == (2, "")
    assert err == ['ignorewhy: invalid path "c/../d"\n']


# --- paths.normalize -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("./src/a.py", (("src", "a.py"), False)),
        ("././x", (("x",), False)),
        ("a\\b/", (("a", "b"), True)),
        ("a/b/", (("a", "b"), True)),
        ("a", (("a",), False)),
        ("a.b/.hidden", (("a.b", ".hidden"), False)),
        ("does/not/exist", (("does", "not", "exist"), False)),
        ("src\\dir\\f.py", (("src", "dir", "f.py"), False)),
    ],
)
def test_normalize_valid(arg, expected):
    assert normalize(arg) == expected


@pytest.mark.parametrize(
    "arg",
    ["", "/a", "\\a", "C:/a", "C:", "a//b", "a/./b", "a/../b", ".", "..", "./", "a/.", "../a"],
)
def test_normalize_invalid(arg):
    with pytest.raises(UsageError) as info:
        normalize(arg)
    assert str(info.value) == f'invalid path "{arg}"'


# --- explain ---------------------------------------------------------------------------------


def test_explain_worked_example(ex):
    code, out, err = invoke(["explain", "--root", str(ex), *EXPLAIN_ARGS])
    assert code == 0
    assert out == lines_of(*EXPLAIN_LINES)
    assert err == []


def test_explain_worked_example_with_cwd_as_root(ex, monkeypatch):
    monkeypatch.chdir(ex)
    code, out, _ = invoke(["explain", *EXPLAIN_ARGS])
    assert code == 0
    assert out == lines_of(*EXPLAIN_LINES)


def test_explain_exclude_file(work):
    (work / "ex.txt").write_bytes(b"*.o\n")
    code, out, err = invoke(["explain", "--exclude", "ex.txt", "tmp/x.o"])
    assert code == 0
    assert out == "tmp/x.o: ignored (ex.txt:1: *.o)\n"
    assert err == []


def test_explain_exclude_equals_form_and_last_wins(work, ex):
    (work / "ex.txt").write_bytes(b"*.o\n")
    code, out, _ = invoke(["explain", "--root", "nodir", "--root=ex", "--exclude=ex.txt", "a.o"])
    assert code == 0
    assert out == "a.o: ignored (ex.txt:1: *.o)\n"


def test_explain_exclude_is_weakest(ex, work):
    (work / "ex.txt").write_bytes(b"*.log\n*.o\n")
    code, out, _ = invoke(["explain", "--root", "ex", "--exclude", "ex.txt", "keep.log", "a.o"])
    assert code == 0
    assert out == lines_of(
        "keep.log: not ignored (.gitignore:3: !keep.log)", "a.o: ignored (ex.txt:2: *.o)"
    )


def test_explain_nothing_ignored_exits_one(ex):
    code, out, err = invoke(["explain", "--root", str(ex), "src/a.py", "README.md"])
    assert code == 1
    assert out == lines_of("src/a.py: not ignored", "README.md: not ignored")
    assert err == []


def test_explain_one_ignored_exits_zero(ex):
    code, out, _ = invoke(["explain", "--root", str(ex), "README.md", "x.log"])
    assert code == 0
    assert out.splitlines()[1] == "x.log: ignored (.gitignore:2: *.log)"


def test_explain_dash_is_a_path(ex):
    code, out, _ = invoke(["explain", "--root", str(ex), "-"])
    assert (code, out) == (1, "-: not ignored\n")


def test_explain_prints_path_as_normalized(ex):
    code, out, _ = invoke(["explain", "--root", str(ex), "./build\\"])
    assert code == 0
    assert out == "build/: ignored (.gitignore:1: build/)\n"


def test_explain_non_utf8_gitignore_reports_its_label(tmp_path):
    (tmp_path / ".gitignore").write_bytes(b"\xff\n")
    code, out, err = invoke(["explain", "--root", str(tmp_path), "a"])
    assert (code, out) == (2, "")
    assert err == ["ignorewhy: .gitignore: input is not valid UTF-8\n"]


# --- filter ----------------------------------------------------------------------------------


def test_filter_stdin_without_file(ex):
    code, out, err = invoke(["filter", "--root", str(ex)], STDIN_PATHS)
    assert (code, out, err) == (0, FILTER_OUT, [])


def test_filter_stdin_with_dash(ex):
    code, out, _ = invoke(["filter", "--root", str(ex), "-"], STDIN_PATHS)
    assert (code, out) == (0, FILTER_OUT)


def test_filter_from_file(ex, tmp_path):
    (tmp_path / "paths.txt").write_bytes(STDIN_PATHS)
    code, out, _ = invoke(["filter", "--root", str(ex), str(tmp_path / "paths.txt")], b"ignored")
    assert (code, out) == (0, FILTER_OUT)


def test_filter_bom_crlf_and_empty_lines(ex):
    data = b"\xef\xbb\xbf" + b"src/main.py\r\n\r\nbuild/x.o\r\n\n.cache/\r\nlogs/a.log\r\nsrc/\r\n"
    code, out, _ = invoke(["filter", "--root", str(ex)], data)
    assert (code, out) == (0, FILTER_OUT)


def test_filter_with_exclude_file(ex, work):
    (work / "ex.txt").write_bytes(b"*.py\n")
    code, out, _ = invoke(["filter", "--root", "ex", "--exclude", "ex.txt"], STDIN_PATHS)
    assert (code, out) == (0, ".cache/\nsrc/\n")


def test_filter_everything_ignored_prints_nothing(ex):
    code, out, err = invoke(["filter", "--root", str(ex)], b"a.log\nbuild/\n")
    assert (code, out, err) == (0, "", [])


def test_filter_empty_input(ex):
    assert invoke(["filter", "--root", str(ex)], b"") == (0, "", [])


def test_filter_prints_paths_as_written(ex):
    code, out, _ = invoke(["filter", "--root", str(ex)], b"./src\\a.py\n")
    assert (code, out) == (0, "./src\\a.py\n")


# --- lint through the command line -----------------------------------------------------------


def test_lint_worked_example(work):
    text = "/a/\n!/a/b/keep.txt\na**b\n./foo\nfoo[\nbar\\\n/a/\n# done\n"
    (work / "ignore.txt").write_bytes(text.encode("utf-8"))
    code, out, err = invoke(["lint", "ignore.txt"])
    assert code == 1
    assert out == lines_of(*LINT_LINES)
    assert err == []


@pytest.mark.parametrize(
    ("content", "summary"),
    [
        (b"foo\n", "ok, 1 rule in 1 file"),
        (b"foo\nbar\n# c\n", "ok, 2 rules in 1 file"),
        (b"", "ok, 0 rules in 1 file"),
    ],
)
def test_lint_clean(work, content, summary):
    (work / "ok.txt").write_bytes(content)
    code, out, _ = invoke(["lint", "ok.txt"])
    assert (code, out) == (0, summary + "\n")


def test_lint_counts_files_and_one_problem(work):
    (work / "a.txt").write_bytes(b"foo\n")
    (work / "b.txt").write_bytes(b"bar\nbaz\n")
    code, out, _ = invoke(["lint", "a.txt", "b.txt"])
    assert (code, out) == (0, "ok, 3 rules in 2 files\n")
    (work / "c.txt").write_bytes(b"foo[\n")
    code, out, _ = invoke(["lint", "a.txt", "c.txt"])
    assert code == 1
    assert out == lines_of('c.txt:1: IW001 invalid pattern: unterminated "[" class', "1 problem")


# --- the tree stays unchanged ----------------------------------------------------------------


def test_runs_do_not_change_the_tree(ex, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lint.txt").write_bytes(b"a\na\n")
    before = snapshot(tmp_path)
    invoke(["explain", "--root", "ex", *EXPLAIN_ARGS])
    invoke(["filter", "--root", "ex"], STDIN_PATHS)
    invoke(["lint", "lint.txt"])
    invoke(["explain", "--root", "nodir", "a"])
    assert snapshot(tmp_path) == before


# --- structure -------------------------------------------------------------------------------

SOURCE_NAMES = {
    "__init__.py", "__main__.py", "errors.py", "globs.py", "rules.py", "ruleset.py",
    "paths.py", "loader.py", "lint.py", "report.py", "cli.py",
}
BANNED_IMPORTS = {"argparse", "subprocess", "socket", "urllib", "http", "re", "fnmatch"}


def source_files():
    return sorted((REPO / "ignorewhy").glob("*.py"))


def test_package_has_exactly_the_named_files():
    assert {path.name for path in source_files()} == SOURCE_NAMES


def test_tests_folder_has_exactly_four_files():
    names = {path.name for path in (REPO / "tests").iterdir() if path.suffix == ".py"}
    assert names == {"test_rules.py", "test_ruleset.py", "test_lint.py", "test_cli.py"}
    assert not (REPO / "tests" / "__init__.py").exists()


@pytest.mark.parametrize("name", ["src"])
def test_no_forbidden_folder(name):
    assert not (REPO / name).exists()


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_source_imports_and_calls(path):
    text = path.read_text(encoding="utf-8")
    for token in ("os.environ", "os.getenv", "os.system"):
        assert token not in text
    imported = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert not imported & BANNED_IMPORTS


def test_main_module_exits_with_main():
    text = (REPO / "ignorewhy" / "__main__.py").read_text(encoding="utf-8")
    assert "sys.exit(main(sys.argv[1:]))" in text


def test_main_reconfigures_streams():
    text = (REPO / "ignorewhy" / "cli.py").read_text(encoding="utf-8")
    expected = '.reconfigure(encoding="utf-8", newline="\\n")'
    assert "sys.stdout" + expected in text
    assert "sys.stderr" + expected in text


# --- docs ------------------------------------------------------------------------------------


def read_text(name):
    return (REPO / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_readme_has_usage_and_examples():
    text = read_text("README.md")
    assert lines_of(*USAGE_LINES) in text
    assert lines_of(*EXPLAIN_LINES) in text
    assert lines_of(*LINT_LINES) in text


@pytest.mark.parametrize(
    "heading",
    [
        "## Install", "## Usage", "## How rules are matched", "## Lint codes", "## Exit codes",
        "## Development",
    ],
)
def test_readme_headings(heading):
    assert heading in read_text("README.md").splitlines()


@pytest.mark.parametrize("command", ["ruff check .", "pytest -q", "python -m ignorewhy"])
def test_readme_mentions_commands(command):
    assert command in read_text("README.md")


def test_license_text():
    text = read_text("LICENSE")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Gulliby-development" in text
