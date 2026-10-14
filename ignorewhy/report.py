"""Output lines of the commands. Every function returns text without a line end."""

USAGE = (
    "usage: ignorewhy explain [--root DIR] [--exclude FILE] PATH...",
    "       ignorewhy filter [--root DIR] [--exclude FILE] [FILE]",
    "       ignorewhy lint FILE...",
)


def error_line(message):
    return f"ignorewhy: {message}"


def explain_line(path_text, decision):
    if decision.rule is None or decision.layer is None:
        return f"{path_text}: not ignored"
    status = "ignored" if decision.ignored else "not ignored"
    rule = decision.rule
    line = f"{path_text}: {status} ({decision.layer.label}:{rule.line}: {rule.text})"
    if decision.via is not None:
        line += f" via {decision.via}"
    return line


def lint_line(label, line, code, message):
    return f"{label}:{line}: {code} {message}"


def _count(problems):
    return problems if isinstance(problems, int) else len(problems)


def lint_summary(problems, rules, files):
    count = _count(problems)
    if count:
        return "1 problem" if count == 1 else f"{count} problems"
    rule_word = "1 rule" if rules == 1 else f"{rules} rules"
    file_word = "1 file" if files == 1 else f"{files} files"
    return f"ok, {rule_word} in {file_word}"
