# =========================
# mamegen/parser_utils.py
# Utility helpers extracted from BlockDSLParser
# =========================

from __future__ import annotations
from datetime import datetime
import re
from typing import Any, List, Optional

from .exceptions import DSLInvalidRuleError


# --------------------
# Basic helpers
# --------------------


def strip_comments(text: str) -> str:
    """Remove trailing '#' comments per line (keeps indentation/whitespace before '#')."""
    out = []
    for line in text.splitlines():
        i = line.find("#")
        if i >= 0:
            line = line[:i]
        out.append(line.rstrip())
    return "\n".join(out)


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and (s[0] == s[-1]) and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def brace_inner_or_none(line: str) -> str:
    """If a single-line {...} exists, return the inner string, otherwise ''."""
    m = re.search(r"\{([\s\S]*)\}", line)
    return m.group(1).strip() if m else ""


# --------------------
# Tokenization / splitting
# --------------------


def split_inline_rules(text: str) -> List[str]:
    """Split one-line rule text at the start of known keywords.
    This mirrors BlockDSLParser._split_inline_rules but without parser state.
    """
    patterns = [
        re.compile(r'(?<!\w)class\s+["\']'),
        re.compile(r"(?<!\\w)string\s*\("),
        re.compile(r"(?<!\\w)enum\\b"),
        re.compile(r"(?<!\\w)regex\\b"),
        re.compile(r"(?<!\\w)charset\\b"),
        re.compile(r"(?<!\\w)fixed\\b"),
        re.compile(r"(?<!\\w)copy\\b"),
        re.compile(r"(?<!\\w)join\\b"),
        re.compile(r"(?<!\\w)seq\\b"),
        re.compile(r"(?<!\\w)date_range\\b"),  # before 'date'
        re.compile(r"(?<!\\w)datetime\\b"),
        re.compile(r"(?<!\\w)date\\b"),
        re.compile(r"(?<!\\w)range\\b"),  # after date_range
        re.compile(r"(?<!\\w)null_probability\\b"),
        re.compile(r"(?<!\\w)allow_null\\b"),
    ]

    i, n = 0, len(text)
    segs: List[str] = []
    start_idx: Optional[int] = None
    in_q: Optional[str] = None
    esc = False

    def match_at(pos: int) -> bool:
        for p in patterns:
            if p.match(text, pos):
                return True
        return False

    while i < n:
        ch = text[i]
        if esc:
            esc = False
            i += 1
            continue
        if ch == "\\":
            esc = True
            i += 1
            continue
        if in_q:
            if ch == in_q:
                in_q = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_q = ch
            i += 1
            continue

        if match_at(i):
            if start_idx is not None:
                seg = text[start_idx:i].strip()
                if seg:
                    segs.append(seg)
            start_idx = i
        i += 1

    if start_idx is None:
        s = text.strip()
        return [s] if s else []
    last = text[start_idx:].strip()
    if last:
        segs.append(last)
    return segs


# --------------------
# Array/value parsing
# --------------------


def vals_in_brackets(s: str) -> List[Any]:
    """Convert "[a,b,...]" into a list of int/float/str with quotes removed."""
    m = re.search(r"\[([\s\S]+?)\]", s)
    vals: List[Any] = []
    if not m:
        return vals
    body = m.group(1)
    parts: List[str] = []
    cur, q, esc = "", None, False
    for ch in body:
        if esc:
            cur += ch
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if q:
            if ch == q:
                q = None
            else:
                cur += ch
            continue
        if ch in ("'", '"'):
            q = ch
            continue
        if ch == ",":
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())

    for p in parts:
        p = p.strip()
        if re.fullmatch(r"-?\d+", p):
            vals.append(int(p))
        elif re.fullmatch(r"-?\d+\.\d+", p):
            vals.append(float(p))
        else:
            vals.append(p.strip().strip('"').strip("'"))
    return vals


def parse_int_list(body: str, line_no: int) -> List[int]:
    """Parse comma separated integers like '2,3, 5' -> [2,3,5].
    Raises DSLInvalidRuleError with given line_no on error.
    """
    items: List[int] = []
    for tok in body.split(","):
        t = tok.strip()
        if not t:
            continue
        if not re.fullmatch(r"-?\d+", t):
            raise DSLInvalidRuleError(line_no, f"INDICES expects integer list: '{t}'")
        items.append(int(t))
    if not items:
        raise DSLInvalidRuleError(line_no, "INDICES list must not be empty")
    return items


def parse_str_list(body: str, line_no: int) -> List[str]:
    """Parse comma separated string list like '"a","b"' -> ["a","b"].
    Quotes optional; preserves inner commas only when quoted.
    """
    parts: List[str] = []
    cur = ""
    q: Optional[str] = None
    esc = False
    for ch in body:
        if esc:
            cur += ch
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if q:
            if ch == q:
                q = None
            else:
                cur += ch
            continue
        if ch in ('"', "'"):
            q = ch
            continue
        if ch == ",":
            tok = cur.strip()
            if tok:
                parts.append(tok)
            cur = ""
        else:
            cur += ch
    tok = cur.strip()
    if tok:
        parts.append(tok)

    out: List[str] = []
    for p in parts:
        s = p.strip().strip('"').strip("'")
        if not s:
            raise DSLInvalidRuleError(line_no, "empty label in LABELS list")
        out.append(s)
    if not out:
        raise DSLInvalidRuleError(line_no, "LABELS list must not be empty")
    return out


import re

_INT_RE = re.compile(r"-?\d+")


def _is_signed_int(s: str) -> bool:
    return bool(_INT_RE.fullmatch(s))


def _infer_number(s: str):
    """文字列を見て int か float に変換する（正規表現なし）。"""
    s = s.strip()
    # まず int として解釈を試みる
    try:
        return int(s)
    except ValueError:
        pass
    # ダメなら float を試みる
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"invalid numeric literal: {s}")


def _parse_ymd_or_die(s: str, line_no: int) -> str:
    """ダブルクォート囲みの YYYY-MM-DD を取り出して妥当性検証して返す。"""
    s = s.strip()
    if not (s.startswith('"') and s.endswith('"')):
        raise DSLInvalidRuleError(
            line_no, 'date must be enclosed in double quotes, e.g. "2025-09-17"'
        )
    inner = s[1:-1]
    try:
        datetime.strptime(inner, "%Y-%m-%d")
    except ValueError:
        raise DSLInvalidRuleError(
            line_no, f"invalid date: {inner} (expected YYYY-MM-DD)"
        )
    return inner
