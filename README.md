<p align="center"><img src="docs/logo.svg" width="96" alt="" /></p>

# ignorewhy

ignorewhy answers the question "why is this path ignored (or not)?" for `.gitignore` files, without needing a git repository. It is for people who debug ignore rules and for people who check ignore files in CI. It names the deciding rule of each path, keeps the paths that are not ignored, and finds rules that cannot work. It never changes any file.

[![CI](https://github.com/Gulliby-development/ignorewhy/actions/workflows/ci.yml/badge.svg)](https://github.com/Gulliby-development/ignorewhy/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

You are staring at a `.gitignore` and a path that is ignored (or not) for no obvious reason, or you want CI to reject ignore rules that can never work. ignorewhy tells you which rule decided, and which line of which file it came from, without a repository, git or a checkout.

## Install

Clone the repository and run the program from its root:

```sh
git clone https://github.com/Gulliby-development/ignorewhy.git
cd ignorewhy
python -m ignorewhy --help
```

It needs Python 3.11 or newer and has no dependencies (standard library only).

## Usage

```
usage: ignorewhy explain [--root DIR] [--exclude FILE] PATH...
       ignorewhy filter [--root DIR] [--exclude FILE] [--ignored] [FILE]
       ignorewhy lint FILE...
```

- `explain` prints one line per PATH and names the rule that decides it.
- `filter` reads one path per line from FILE (or from standard input without FILE or with `-`) and prints the paths that are not ignored; with `--ignored` it prints the paths that are ignored instead.
- `lint` reads each FILE as one ignore file and reports rules that cannot work.

Options of `explain` and `filter`: `--root DIR` is the directory that holds the root `.gitignore` (default `.`); `--exclude FILE` is an extra ignore file with the weakest rules. Write them as `--opt VALUE` or `--opt=VALUE`; the last one wins. `lint` takes no options. Paths are never looked up on disk: a trailing `/` marks a directory. `--ignored` is an option of `filter` only and takes no value.

Example: in a folder `ex` with the root `.gitignore` (lines `build/`, `*.log`, `!keep.log`, `/dist`) and `docs/.gitignore` (lines `*.tmp`, `!/notes.tmp`), this command run in `ex`

```
ignorewhy explain build/app.js build/ a.log keep.log dist src/dist/x.txt docs/x.tmp docs/notes.tmp README.md
```

prints

```
build/app.js: ignored (.gitignore:1: build/) via build/
build/: ignored (.gitignore:1: build/)
a.log: ignored (.gitignore:2: *.log)
keep.log: not ignored (.gitignore:3: !keep.log)
dist: ignored (.gitignore:4: /dist)
src/dist/x.txt: not ignored
docs/x.tmp: ignored (docs/.gitignore:1: *.tmp)
docs/notes.tmp: not ignored (docs/.gitignore:2: !/notes.tmp)
README.md: not ignored
```

Example: in the same folder `ex`, `ignorewhy filter --ignored` with the standard input lines `src/main.py`, `build/x.o`, `.cache/`, `logs/a.log` and `src/` prints the two ignored lines `build/x.o` and `logs/a.log`, in input order; without `--ignored` it prints the other three.

Example: the file `ignore.txt` has the lines `/a/`, `!/a/b/keep.txt`, `a**b`, `./foo`, `foo[`, `bar\` (one trailing backslash), `/a/` and `# done`. The command `ignorewhy lint ignore.txt` prints

```
ignore.txt:2: IW003 cannot re-include "a/b/keep.txt": parent directory "a" is excluded by line 1
ignore.txt:3: IW004 "**" only works as a whole path segment
ignore.txt:4: IW005 pattern starts with "./" and never matches
ignore.txt:5: IW001 invalid pattern: unterminated "[" class
ignore.txt:6: IW001 invalid pattern: trailing backslash
ignore.txt:7: IW002 duplicate of line 1
6 problems
```

Example: the file `notes.txt` has the lines `build/ # output` and `*.log`. The command `ignorewhy lint notes.txt` prints

```
notes.txt:1: IW006 "#" after a space is part of the pattern, not a comment
1 problem
```

## How rules are matched

- An ignore file is UTF-8; one leading BOM is skipped and lines are split at LF. Per line, one trailing CR and trailing spaces are removed (a space escaped by a backslash stays). An empty line or a line that starts with `#` is no rule.
- A leading `!` negates the rule. A trailing `/` makes the rule directory-only. A rule is anchored when its body still contains a `/`; one leading `/` is removed.
- The body is split at `/` into segments. A segment `**` stands for zero or more path components (one or more when it is the last segment). Any other segment matches exactly one component: `*` any run of characters, `?` one character, `[...]` a class (`!` or `^` negates, `a-z` ranges), a backslash makes the next character literal. `**` inside a longer segment is just `*`. Matching is case-sensitive and a leading dot is not special.
- An unanchored rule is tested against the last component of the path only.
- A `[` without closing `]`, a trailing backslash or an empty segment makes the rule invalid; it matches nothing.
- Layers, weakest first: the `--exclude` file, the root `.gitignore`, then the `.gitignore` of each ancestor directory of the path from shallow to deep. A layer applies only below its own directory, and its rules see the path without that directory. The deepest layer with a matching rule decides; inside a layer the last matching rule wins. A `!` rule means not ignored.
- A path is also ignored when one of its ancestor directories (shortest first) is ignored, so a path below an ignored directory cannot be re-included.

Intended differences from git: no POSIX classes (`[[:alpha:]]`), no `core.ignorecase`, no symbolic links, no tracked files and no global ignore files.

## Lint codes

- `IW001`: an invalid rule (unterminated `[` class, trailing backslash or empty path segment). An invalid rule gets only this code.
- `IW002`: a rule whose text equals an earlier valid rule.
- `IW003`: a `!` rule for an anchored literal path whose parent directory is already excluded by an earlier rule of the same file, so it cannot re-include.
- `IW004`: a segment that contains `**` together with other characters; `**` only works as a whole segment.
- `IW005`: a rule that starts with `./` or `../` and never matches.
- `IW006`: a rule with an unescaped space directly followed by `#`, such as `build/ # output`. A `#` starts a comment only at the start of a line; here it is part of the pattern, so the rule matches nothing you meant. Write the comment on its own line, or escape the space with a backslash if the name really contains it. A rule that is already invalid (`IW001`) gets no `IW006`.
- `IW007`: a rule with a backslash before an ordinary character, that is any character except a space and `! # * - ? [ ] ^ \`. A backslash only escapes the next character, so `build\out` means the name `buildout`, not the path `build/out`; write `/` between path segments. Only the first such backslash of a rule is reported, as `\o` is the same as `o`. A rule that is already invalid (`IW001`) gets no `IW007`.

## Exit codes

- `explain`: 0 when at least one path is ignored, 1 when nothing is ignored.
- `filter`: 0.
- `lint`: 0 when clean, 1 when there are problems.
- Every command: 2 for an error (one line `ignorewhy: MESSAGE` on standard error, nothing on standard output).

## Development

Run the checks from the repository root:

```sh
python -m pip install pytest ruff
python -m ruff check .
python -m pytest -q
```

## License

MIT, see [LICENSE](LICENSE).

---

Built with BAKED, an open-source coding agent (bench loop round 19).
