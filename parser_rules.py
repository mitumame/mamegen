# =========================
# mamegen/parser_rules.py
# Rule parsing helpers extracted from BlockDSLParser
# =========================

from __future__ import annotations
import re
from typing import Any, Dict, List

from .exceptions import DSLInvalidRuleError
from . import parser_utils as pu


# -------------------------
# 共通ヘルパ
# -------------------------
def extract_rule_arg(body: str, rule: str) -> str:
    """rule の後ろの引数部分を抽出。失敗時は ValueError 送出。"""
    s = body.strip()
    prefix = rule + " "
    if not s.startswith(prefix):
        raise ValueError(f"{rule} syntax must start with '{prefix}'")
    # rule名 + スペースを取り除いた後ろ全部
    return s[len(prefix) :].strip()


# ------------------------------------------------------------
# ルール解析関数（parse_*）の設計方針
# - すべて (body: str, line_no: int) -> Dict[str, Any] を返す
# - 返り値は「正規化済みルール」のディクショナリ（generator 側に渡せる形）
# - エラー時は DSLInvalidRuleError(line_no, ...) を送出
# - allow_null / null_probability は他ルールと同列（1 行 1 ルール原則）
# ------------------------------------------------------------


# --------------
# NULL 制御
# --------------
def parse_allow_null(body: str, line_no: int) -> Dict[str, Any]:
    """allow_null true/false を解析する。"""
    tok = body.strip().split()
    if len(tok) != 2 or tok[0] != "allow_null":
        raise DSLInvalidRuleError(line_no, "allow_null syntax: 'allow_null true|false'")
    val = tok[1].lower()
    if val not in ("true", "false"):
        raise DSLInvalidRuleError(line_no, "allow_null must be true/false")
    return {"type": "allow_null", "value": (val == "true")}


def parse_null_probability(body: str, line_no: int) -> Dict[str, Any]:
    """null_probability 0.0..1.0 を解析する。"""
    tok = body.strip().split()
    if len(tok) != 2 or tok[0] != "null_probability":
        raise DSLInvalidRuleError(
            line_no, "null_probability syntax: 'null_probability <0..1>'"
        )
    try:
        p = float(tok[1])
    except ValueError:
        raise DSLInvalidRuleError(line_no, "null_probability must be a number")
    if not (0.0 <= p <= 1.0):
        raise DSLInvalidRuleError(line_no, "null_probability must be between 0 and 1")
    return {"type": "null_probability", "value": p}


# --------------
# 逐次番号（seq）
# --------------
def parse_seq(body: str, line_no: int) -> Dict[str, Any]:
    """seq 1.. / seq 1..100 （上限省略は open range）。"""
    try:
        arg = extract_rule_arg(body, "seq")
    except ValueError as e:
        raise DSLInvalidRuleError(
            line_no, str(e) + "  ('seq <start>' or 'seq <start>..<end>')"
        )

    arg = arg.strip()

    # 「..」なし = 単一数値 → open range 扱い（end=None）
    if ".." not in arg:
        if not pu._is_signed_int(arg):
            raise DSLInvalidRuleError(line_no, "seq start must be an integer")
        start = int(arg)
        return {"type": "seq", "start": start, "end": None, "step": 1}

    # 「..」あり
    parts = arg.split("..", 1)
    if len(parts) != 2:
        raise DSLInvalidRuleError(line_no, "seq syntax must contain a single '..'")

    start_str, end_str = parts[0].strip(), parts[1].strip()

    if not pu._is_signed_int(start_str):
        raise DSLInvalidRuleError(line_no, "seq start must be an integer")
    start = int(start_str)

    if end_str == "":
        end = None  # open range
    else:
        if not pu._is_signed_int(end_str):
            raise DSLInvalidRuleError(line_no, "seq end must be an integer or empty")
        end = int(end_str)
        if start > end:
            raise DSLInvalidRuleError(line_no, "seq start must be <= end")

    return {"type": "seq", "start": start, "end": end, "step": 1}


# --------------
# 桁数(SEQ用、ゼロパディング)
# --------------
def parse_digits(body: str, line_no: int) -> Dict[str, Any]:
    """digits 4 を解析（seq用、ゼロパディング桁数）。"""
    try:
        arg = extract_rule_arg(body, "digits")
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('digits <n>')")

    arg = arg.strip()
    if not (arg.isascii() and arg.isdigit()):
        raise DSLInvalidRuleError(
            line_no, "digits syntax: 'digits <n>' (n must be positive integer)"
        )
    n = int(arg)
    if n <= 0:
        raise DSLInvalidRuleError(line_no, "digits must be > 0")
    return {"type": "digits", "n": n}


# --------------
# ステップ数(SEQ用)
# --------------
def parse_step(body: str, line_no: int) -> Dict[str, Any]:
    """step 1 を解析（seq 用）。"""
    try:
        arg = extract_rule_arg(body, "step")
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('step <n>')")

    arg = arg.strip()
    if not (arg.isascii() and arg.isdigit()):
        raise DSLInvalidRuleError(
            line_no, "step syntax: 'step <n>' (n must be positive integer)"
        )
    n = int(arg)
    if n <= 0:
        raise DSLInvalidRuleError(line_no, "step must be > 0")
    return {"type": "step", "n": n}


# --------------
# 文字種/長さ(string用)
# --------------
_ALLOWED_CHARSETS = {"alphabet", "lower", "upper", "number", "hex", "symbol"}


def parse_charset(body: str, line_no: int) -> Dict[str, Any]:
    """charset alphabet | lower | upper | number | hex | symbol を解析。"""
    try:
        arg = extract_rule_arg(body, "charset")
    except ValueError as e:
        raise DSLInvalidRuleError(
            line_no, str(e) + "  ('charset alphabet|lower|upper|number|hex|symbol')"
        )

    name = arg.strip().lower()
    if name not in _ALLOWED_CHARSETS:
        raise DSLInvalidRuleError(
            line_no,
            f"unsupported charset '{name}' (allowed: {', '.join(sorted(_ALLOWED_CHARSETS))})",
        )
    return {"type": "charset", "name": name}


def parse_length(body: str, line_no: int) -> Dict[str, Any]:
    """length 8 を解析。"""
    try:
        arg = extract_rule_arg(body, "length")
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('length <n>')")

    arg = arg.strip()
    if not (arg.isascii() and arg.isdigit()):
        raise DSLInvalidRuleError(
            line_no, "length syntax: 'length <n>' (n must be positive integer)"
        )
    n = int(arg)
    if n <= 0:
        raise DSLInvalidRuleError(line_no, "length must be > 0")
    return {"type": "length", "n": n}


# --------------
# 列挙/固定/コピー/結合
# --------------
def parse_enum(body: str, line_no: int) -> Dict[str, Any]:
    """enum [a,b,"c"] を解析。"""
    try:
        arg = extract_rule_arg(body, "enum")
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('enum [v1,v2,...]')")

    s = arg.strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise DSLInvalidRuleError(line_no, "enum syntax: 'enum [v1,v2,...]'")

    vals = pu.vals_in_brackets(s)
    if not vals:
        raise DSLInvalidRuleError(line_no, "enum requires non-empty list")

    return {"type": "enum", "values": vals}


def parse_fixed(body: str, line_no: int) -> Dict[str, Any]:
    """fixed "value" を解析（数値/文字列いずれも可）。"""
    try:
        arg = extract_rule_arg(body, "fixed").strip()
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('fixed <value>')")

    # 引数がクォートなら文字列、そうでなければ数値判定（int/float）
    if len(arg) >= 2 and arg[0] == '"' and arg[-1] == '"':
        v: Any = pu.unquote(arg)
    else:
        try:
            v = pu._infer_number(arg)
        except ValueError:
            # 数値でもクォートでもない → クォート忘れの文字列として扱わずエラーにする
            raise DSLInvalidRuleError(
                line_no, "fixed value must be a number or a quoted string"
            )
    return {"type": "fixed", "value": v}


def parse_copy(body: str, line_no: int) -> Dict[str, Any]:
    """copy "name" あるいは copy 3 の形式を解析。"""
    try:
        arg = extract_rule_arg(body, "copy").strip()
    except ValueError:
        raise DSLInvalidRuleError(line_no, "copy syntax must start with 'copy '")

    # ダブルクォート囲み（列ラベル指定）
    if len(arg) >= 2 and arg[0] == '"' and arg[-1] == '"':
        return {"type": "copy", "by": "label", "key": arg[1:-1]}

    # 半角数字のみ（1始まりの列インデックス）
    if arg.isascii() and arg.isdigit():
        idx = int(arg)
        if idx <= 0:
            raise DSLInvalidRuleError(line_no, "copy index must be >= 1")
        return {"type": "copy", "by": "index", "key": idx}

    raise DSLInvalidRuleError(line_no, 'copy arg must be "label" or integer')


def parse_array_literal(body: str) -> List[Dict[str, str]]:
    """
    ["PROMO-", code_num] のような配列リテラルを解析。
    - 先頭と末尾は必ず [] であること
    - 要素は "..." (文字列リテラル) または識別子
    - カンマ区切り、空白は自由
    戻り値は {"lit": "..."} or {"ref": "..."} の配列に正規化。
    """
    s = body.strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise ValueError(f"配列は [] で囲む必要があります: {body}")

    inner = s[1:-1].strip()
    if not inner:
        return []

    items: List[Dict[str, str]] = []
    for raw in inner.split(","):
        token = raw.strip()
        if not token:
            raise ValueError(f"空の要素は不正: {body}")

        # 文字列リテラル
        if (len(token) >= 2) and token[0] == '"' and token[-1] == '"':
            items.append({"literal": token[1:-1]})
        else:
            # 識別子: 英数字と_のみ許可
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
                raise ValueError(f"不正な識別子: {token}")
            items.append({"reference": token})

    return items


def parse_join(body: str, line_no: int) -> Dict[str, Any]:
    """
    join ["user ", user_id, " at ", ts]
    -> {"type":"join","items":[{"literal":"user "},{"reference":"user_id"},{"literal":" at "},{"reference":"ts"}]}
    """
    try:
        arg = extract_rule_arg(body, "join")
        items = parse_array_literal(arg.strip())  # "join " の後ろを全部引数とみなす
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, f"join syntax error: {e}")

    return {"type": "join", "items": items}


# --------------
# 数値レンジ
# --------------
def parse_range(body: str, line_no: int) -> Dict[str, Any]:
    """range 1..10 や range -1.0..1.0 を解析（整数/浮動小数を許可）。"""
    try:
        arg = extract_rule_arg(body, "range")
    except ValueError as e:
        raise DSLInvalidRuleError(line_no, str(e) + "  ('range <n>')")

    # 「..」なし = 単一数値 → range 扱い（end=None）
    if ".." not in arg:
        try:
            start = pu._infer_number(arg)
        except ValueError:
            raise DSLInvalidRuleError(line_no, "range start must be a valid number")
        return {"type": "range", "min": start, "max": None}

    # 「..」あり
    parts = arg.split("..", 1)
    if len(parts) != 2:
        raise DSLInvalidRuleError(line_no, "range syntax must contain a single '..'")
    try:
        min_val = pu._infer_number(parts[0].strip())
        max_val = pu._infer_number(parts[1].strip())
    except ValueError:
        raise DSLInvalidRuleError(line_no, "range syntax: range <num>..<num>")

    if isinstance(min_val, float) or isinstance(max_val, float):
        min_val, max_val = float(min_val), float(max_val)

    if min_val > max_val:
        raise DSLInvalidRuleError(line_no, "range lower bound must be <= upper bound")
    return {"type": "range", "min": min_val, "max": max_val}


# --------------
# 日付/日時
# --------------
def parse_date_range(body: str, line_no: int) -> Dict[str, Any]:
    """
    date_range "YYYY-MM-DD".."YYYY-MM-DD"
    """
    try:
        arg = extract_rule_arg(body, "date_range").strip()
    except ValueError:
        raise DSLInvalidRuleError(
            line_no, 'date_range syntax: date_range "YYYY-MM-DD".."YYYY-MM-DD"'
        )

    # ".." で左右を分割（余分な空白は許容）
    if ".." not in arg:
        raise DSLInvalidRuleError(
            line_no, 'date_range syntax: date_range "YYYY-MM-DD".."YYYY-MM-DD"'
        )
    left, right = [x.strip() for x in arg.split("..", 1)]
    if not left or not right:
        raise DSLInvalidRuleError(
            line_no, 'date_range syntax: date_range "YYYY-MM-DD".."YYYY-MM-DD"'
        )

    start = pu._parse_ymd_or_die(left, line_no)
    end = pu._parse_ymd_or_die(right, line_no)

    if start > end:
        raise DSLInvalidRuleError(line_no, "date_range start must be <= end")

    return {"type": "date_range", "start": start, "end": end}


def parse_date(body: str, line_no: int) -> Dict[str, Any]:
    """just 'date'（括弧記法なし）。"""
    if body.strip() != "date":
        raise DSLInvalidRuleError(
            line_no, "date syntax: just 'date' (use date_range for bounds)"
        )
    return {"type": "date"}


def parse_datetime(body: str, line_no: int) -> Dict[str, Any]:
    """just 'datetime'（括弧記法なし）。"""
    if body.strip() != "datetime":
        raise DSLInvalidRuleError(line_no, "datetime syntax: just 'datetime'")
    return {"type": "datetime"}


# --------------
# 参照系
# --------------
def parse_reference(body: str, line_no: int) -> Dict[str, Any]:
    """
    reference "Q1"
    """
    try:
        arg = extract_rule_arg(body, "reference").strip()
    except ValueError:
        raise DSLInvalidRuleError(line_no, 'reference syntax: reference "KEY"')

    # クォートで囲まれていない場合はエラー
    if not (arg.startswith('"') and arg.endswith('"')):
        raise DSLInvalidRuleError(
            line_no, "reference key must be enclosed in double quotes"
        )

    key = pu.unquote(arg)
    if not key:
        raise DSLInvalidRuleError(line_no, "reference key must not be empty")

    return {"type": "reference", "key": key}


def parse_output(body: str, line_no: int) -> Dict[str, Any]:
    """
    output label | output value
    """
    arg = body.strip()
    if arg == "output label":
        return {"type": "output", "side": "label"}
    if arg == "output value":
        return {"type": "output", "side": "value"}
    raise DSLInvalidRuleError(line_no, "output syntax: output label|value")


def parse_value_source(body: str, line_no: int) -> Dict[str, Any]:
    """
    value_source # 自列より左の同KEYの label 列を自動探索（直近）
    value_source "colname" # 明示的に参照元列を指定
    """
    arg = body.strip()
    if arg == "value_source":  # 自動探索(直近)
        return {"type": "value_source", "auto": True}

    # 明示的に列名指定
    if arg.startswith("value_source "):
        target = arg[len("value_source ") :].strip()
        if not (target.startswith('"') and target.endswith('"')):
            raise DSLInvalidRuleError(
                line_no, 'value_source syntax: value_source or value_source "colname"'
            )
        colname = pu.unquote(target)
        if not colname:
            raise DSLInvalidRuleError(
                line_no, "value_source column name must not be empty"
            )

        return {"type": "value_source", "col": colname}

    raise DSLInvalidRuleError(
        line_no, 'value_source syntax: value_source or value_source "colname"'
    )


# ------------------------------------------------------------
# ルール名 → 解析関数のディスパッチテーブル
# BlockDSLParser 側で import して利用する想定
# ------------------------------------------------------------
RULE_TABLE = {
    # null control
    "allow_null": parse_allow_null,
    "null_probability": parse_null_probability,
    # seq
    "seq": parse_seq,
    "digits": parse_digits,
    "step": parse_step,
    # charset / string length
    "charset": parse_charset,
    "length": parse_length,
    # enum/fixed/copy/join
    "enum": parse_enum,
    "fixed": parse_fixed,
    "copy": parse_copy,
    "join": parse_join,
    # range/number
    "range": parse_range,
    # date/datetime
    "date_range": parse_date_range,
    "date": parse_date,
    "datetime": parse_datetime,
    # reference (new)
    "reference": parse_reference,
    "output": parse_output,
    "value_source": parse_value_source,
}
