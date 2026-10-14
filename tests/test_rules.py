"""Tests for glob segments, path matching and rule parsing."""

import dataclasses
import time

import pytest

from ignorewhy.globs import (
    DOUBLE_STAR,
    PatternError,
    compile_segment,
    match_path,
    match_segment,
)
from ignorewhy.rules import Rule, parse_text

BS = chr(92)
NL = chr(10)
CR = chr(13)
BOM = chr(0xFEFF)
UNTERM = 'invalid pattern: unterminated "[" class'
TRAIL = 'invalid pattern: trailing backslash'
EMPTY = 'invalid pattern: empty path segment'


def seg(pattern, text):
    return match_segment(compile_segment(pattern), text)


def rule_of(text):
    rules = parse_text(text)
    assert len(rules) == 1
    return rules[0]


@pytest.mark.parametrize(
    ('pattern', 'text', 'expected'),
    [
        ('*.txt', '.x.txt', True),
        ('*.txt', 'a.txt', True),
        ('*.txt', 'a.txt2', False),
        ('a*', 'a', True),
        ('a*', 'abc', True),
        ('a*', 'b', False),
        ('*', '', True),
        ('*', '.hidden', True),
        ('?', 'a', True),
        ('?', '', False),
        ('?', 'ab', False),
        ('a?c', 'abc', True),
        ('a?c', 'ac', False),
        ('a*c', 'abbc', True),
        ('a*c', 'abd', False),
        ('[!a]x', 'bx', True),
        ('[!a]x', 'ax', False),
        ('[^a]x', 'bx', True),
        ('[^a]x', 'ax', False),
        ('[a-c]x', 'ax', True),
        ('[a-c]x', 'bx', True),
        ('[a-c]x', 'cx', True),
        ('[a-c]x', 'dx', False),
        ('[]a]', ']', True),
        ('[]a]', 'a', True),
        ('[]a]', 'b', False),
        ('[!]a]', 'b', True),
        ('[!]a]', ']', False),
        ('[' + BS + ']]', ']', True),
        ('[' + BS + ']]', 'a', False),
        (BS + '#x', '#x', True),
        (BS + '!x', '!x', True),
        ('x' + BS + ' ', 'x ', True),
        ('x' + BS + ' ', 'x', False),
        (BS + '*', '*', True),
        (BS + '*', 'a', False),
        (BS + '?', '?', True),
        (BS + '?', 'a', False),
        ('a**b', 'aXXb', True),
        ('a**b', 'ab', True),
        ('a**b', 'ac', False),
        ('Foo', 'foo', False),
        ('Foo', 'Foo', True),
        ('[A-Z]', 'a', False),
        ('[[:alpha:]]', 'a', False),
        ('[[:alpha:]]', 'a]', True),
    ],
)
def test_segment_forms(pattern, text, expected):
    assert seg(pattern, text) is expected


def test_compile_segment_returns_tuple():
    assert isinstance(compile_segment('a*b'), tuple)


def test_star_run_collapses():
    assert compile_segment('a**b') == compile_segment('a*b')


def test_pattern_error_is_value_error():
    assert issubclass(PatternError, ValueError)


@pytest.mark.parametrize(
    ('pattern', 'message'),
    [
        ('foo[', UNTERM),
        ('[', UNTERM),
        ('[!', UNTERM),
        ('[]', UNTERM),
        ('bar' + BS, TRAIL),
        (BS, TRAIL),
    ],
)
def test_pattern_errors(pattern, message):
    with pytest.raises(PatternError) as info:
        compile_segment(pattern)
    assert str(info.value) == message


def path_match(segments, parts):
    compiled = [s if s == DOUBLE_STAR else compile_segment(s) for s in segments]
    return match_path(compiled, parts)


@pytest.mark.parametrize(
    ('segments', 'parts', 'expected'),
    [
        (['a', 'b'], ('a', 'b'), True),
        (['a', 'b'], ('a',), False),
        (['a'], ('a', 'b'), False),
        (['**', 'b'], ('b',), True),
        (['**', 'b'], ('a', 'b'), True),
        (['**', 'b'], ('a', 'c'), False),
        (['a', '**', 'b'], ('a', 'b'), True),
        (['a', '**', 'b'], ('a', 'x', 'y', 'b'), True),
        (['a', '**', 'b'], ('a', 'x'), False),
        (['a', '**'], ('a', 'b'), True),
        (['a', '**'], ('a', 'b', 'c'), True),
        (['a', '**'], ('a',), False),
        (['**'], ('a',), True),
        (['**'], (), False),
    ],
)
def test_match_path(segments, parts, expected):
    assert path_match(segments, parts) is expected


@pytest.mark.parametrize(
    ('text', 'parts', 'is_dir', 'expected'),
    [
        ('foo', ('a', 'b', 'foo'), False, True),
        ('foo', ('foo',), False, True),
        ('foo', ('a', 'foo', 'b'), False, False),
        ('foo/', ('a', 'foo'), True, True),
        ('foo/', ('a', 'foo'), False, False),
        ('/foo', ('a', 'foo'), False, False),
        ('/foo', ('foo',), False, True),
        ('a/b', ('a', 'b'), False, True),
        ('a/b', ('x', 'a', 'b'), False, False),
        ('a/**', ('a', 'b'), False, True),
        ('a/**', ('a',), True, False),
        ('**/b', ('b',), False, True),
        ('**/b', ('a', 'b'), False, True),
        ('a/**/b', ('b',), False, False),
        ('a/**/b', ('a', 'b'), False, True),
        ('a/**/b', ('a', 'x', 'y', 'b'), False, True),
        ('*.txt', ('.x.txt',), False, True),
        ('**', ('a',), False, True),
        ('a//b', ('a', 'b'), False, False),
        ('foo[', ('foo[',), False, False),
        ('[!a]x', ('bx',), False, True),
        (BS + '#x', ('#x',), False, True),
        (BS + '!x', ('!x',), False, True),
        ('x' + BS + ' ', ('x ',), False, True),
        ('a**b', ('aXXb',), False, True),
        ('!keep.log', ('keep.log',), False, True),
    ],
)
def test_rule_matches(text, parts, is_dir, expected):
    assert rule_of(text).matches(parts, is_dir) is expected


def test_bom_and_crlf_example():
    text = BOM + '# c' + CR + NL + 'foo' + CR + NL + CR + NL + 'bar ' + CR + NL
    rules = parse_text(text)
    assert [(r.text, r.line) for r in rules] == [('foo', 2), ('bar', 4)]


def test_only_one_cr_removed():
    assert rule_of('foo' + CR + CR + NL).text == 'foo' + CR


def test_bom_only_once():
    assert parse_text(BOM + BOM + 'foo')[0].text == BOM + 'foo'


def test_bom_not_skipped_inside():
    assert parse_text('a' + NL + BOM + 'foo')[1].text == BOM + 'foo'


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('foo   ', 'foo'),
        ('foo\t', 'foo\t'),
        ('foo' + BS + ' ', 'foo' + BS + ' '),
        ('foo' + BS + ' ' + BS + ' ', 'foo' + BS + ' ' + BS + ' '),
        ('foo' + BS + BS + ' ', 'foo' + BS + BS),
        ('foo' + BS + '  ', 'foo' + BS + ' '),
        (' foo', ' foo'),
    ],
)
def test_trailing_spaces(text, expected):
    assert rule_of(text).text == expected


@pytest.mark.parametrize(
    'text', ['', NL + NL, '# comment', '   ', '#', '  ' + NL + '#x' + NL]
)
def test_no_rules(text):
    assert parse_text(text) == []


def test_line_numbers_count_every_line():
    rules = parse_text(NL.join(['# c', '', 'foo', '', '', 'bar']))
    assert [r.line for r in rules] == [3, 6]


def test_escaped_hash_is_rule():
    rule = rule_of(BS + '#x')
    assert rule.text == BS + '#x'
    assert not rule.negated


def test_escaped_bang_is_not_negated():
    assert rule_of(BS + '!x').negated is False


def test_negation_flags():
    rule = rule_of('!keep.log')
    assert rule.negated
    assert not rule.dir_only
    assert not rule.anchored
    assert rule.error is None


def test_plain_rule_is_not_negated():
    assert rule_of('keep.log').negated is False


def test_dir_only_flag():
    rule = rule_of('build/')
    assert rule.dir_only
    assert not rule.anchored


@pytest.mark.parametrize(
    ('text', 'anchored'),
    [('/dist', True), ('a/b', True), ('dist', False)],
)
def test_anchored_flag(text, anchored):
    assert rule_of(text).anchored is anchored


def test_negated_dir_only_anchored():
    rule = rule_of('!/a/')
    assert rule.negated and rule.dir_only and rule.anchored


@pytest.mark.parametrize('text', ['!', '/', '!/'])
def test_empty_body_is_no_rule(text):
    assert parse_text(text) == []


@pytest.mark.parametrize(
    ('text', 'error', 'parts'),
    [
        ('a//b', EMPTY, ('a', 'b')),
        ('foo[', UNTERM, ('foo[',)),
        ('bar' + BS, TRAIL, ('bar' + BS,)),
        ('a//b[', EMPTY, ('a', 'b')),
        ('a[/b', UNTERM, ('a[', 'b')),
    ],
)
def test_invalid_rules(text, error, parts):
    rule = rule_of(text)
    assert rule.error == error
    assert rule.matches(parts, True) is False
    assert rule.matches(parts, False) is False


def test_valid_rule_has_no_error():
    assert rule_of('a/b').error is None


def test_rule_is_frozen():
    rule = rule_of('foo')
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.text = 'bar'


def test_rule_is_rule_instance():
    assert isinstance(rule_of('foo'), Rule)


def test_performance_no_exponential_backtracking():
    items = compile_segment('*a*a*a*a*a*a*a*a*b')
    text = 'a' * 5000
    start = time.perf_counter()
    result = match_segment(items, text)
    elapsed = time.perf_counter() - start
    assert result is False
    assert elapsed < 2.0


def test_performance_matching_case():
    items = compile_segment('*a*a*a*a*a*a*a*a*b')
    assert match_segment(items, 'a' * 5000 + 'b') is True
