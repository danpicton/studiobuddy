"""Turn common Markdown into readable speech without changing the saved reply."""

import re
from html import unescape


def _inline(text):
    # Keep link labels, not destinations or reference definitions.
    text = re.sub(r"!?\[([^\]]*)\]\((?:[^()\n]|\([^()\n]*\))*\)", r"\1", text)
    text = re.sub(r"!?\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"(`+)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1", r"\2", text)
    # Word boundaries preserve identifiers such as bass_gain.
    text = re.sub(r"(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+.!>|~-])", r"\1", text)
    return unescape(text).strip()


def _sentence(text):
    text = _inline(text)
    return text + "." if text and text[-1] not in ".!?:;" else text


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_separator(line):
    return "|" in line and all(re.fullmatch(r":?-{3,}:?", c) for c in _cells(line))


def speech_text(text):
    """Remove common layout syntax; verbalize table rows with their column labels.

    This is a conservative speech fallback, not a full Markdown or maths renderer.
    Code blocks remain available in the original text instead of being spelled out.
    """
    lines = text.splitlines()
    output = []
    fence = None
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if fence:
            if re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line):
                fence = None
            continue
        opening = re.match(r"^(`{3,}|~{3,})", line)
        if opening:
            fence = opening[1]
            output.append("Code is available in the text reply.")
            continue
        if not line or re.fullmatch(r"[\s#*_`~|:=\-]+", line):
            continue
        if re.match(r"^\[[^\]]+\]:\s+\S+", line):
            continue
        if index < len(lines) and _table_separator(lines[index]):
            headers = _cells(line)
            index += 1
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                values = _cells(lines[index])
                for column, value in enumerate(values):
                    label = _inline(headers[column]) if column < len(headers) else ""
                    if value:
                        output.append(_sentence(f"{label}: {value}" if label else value))
                index += 1
            continue
        heading = re.match(r"^#{1,6}(?:\s+|$)(.*?)(?:\s+#+)?$", line)
        if heading:
            output.append(_sentence(heading[1]))
            continue
        # A setext underline is a heading, not a spoken string of dashes.
        if index < len(lines) and re.fullmatch(r"\s*(?:={3,}|-{3,})\s*", lines[index]):
            output.append(_sentence(line))
            index += 1
            continue
        line = re.sub(r"^(?:>\s*)+", "", line)
        bullet = re.match(r"^(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.*)$", line)
        output.append(_sentence(bullet[1]) if bullet else _inline(line))
    return " ".join(" ".join(output).split())
