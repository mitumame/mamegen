# =========================
# mamegen/common_generator.py
# =========================
import csv, json, random, re, string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ----- charset pools -----
CHARSETS = {
    "lower": string.ascii_lowercase,  # a-z
    "upper": string.ascii_uppercase,  # A-Z
    "alphabet": string.ascii_letters,  # a-zA-Z
    "number": string.digits,  # 0-9
    "hex": string.digits + "ABCDEF",  # 0-9A-F
    "symbol": string.punctuation,  # !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~
}


def _pool_from_charset(toks: Optional[List[str]]) -> str:
    if not toks:
        return string.ascii_letters + string.digits
    pool_set = set()
    for t in toks:
        if t == "alphabet":
            pool_set.update(CHARSETS["alphabet"])
        elif t in CHARSETS:
            pool_set.update(CHARSETS[t])
        else:
            # 未知トークンは無視
            pass
    return "".join(sorted(pool_set)) or (string.ascii_letters + string.digits)


# ----- date format -----
def _to_py_dt_fmt(fmt: str) -> str:
    # "YYYY-MM-DD HH:mm:ss" -> "%Y-%m-%d %H:%M:%S"
    s = fmt
    s = s.replace("YYYY", "%Y")
    s = s.replace("HH", "%H")
    s = s.replace("mm", "%M")  # 分
    s = s.replace("MM", "%m")  # 月
    s = s.replace("DD", "%d")
    s = s.replace("ss", "%S")
    return s


def _parse_date_like(s: str) -> datetime:
    # "YYYY-MM-DD" or "YYYY/MM/DD" or with time
    s_norm = s.strip()
    # 汎用: "/" を "-" に
    s_try = s_norm.replace("/", "-")
    # with time?
    if " " in s_try:
        return datetime.strptime(s_try, "%Y-%m-%d %H:%M:%S")
    else:
        return datetime.strptime(s_try, "%Y-%m-%d")


# ----- regex minimal generator -----
def _expand_class(clz: str) -> List[str]:
    # "A-Z0-9" -> ['A'..'Z'] + ['0'..'9']
    out = []
    i = 0
    while i < len(clz):
        if i + 2 < len(clz) and clz[i + 1] == "-":
            out.extend([chr(c) for c in range(ord(clz[i]), ord(clz[i + 2]) + 1)])
            i += 3
        else:
            out.append(clz[i])
            i += 1
    return out


# ----- primitives -----
def _rand_string(n: int, pool: Optional[str] = None) -> str:
    p = pool or (string.ascii_letters + string.digits)
    return "".join(random.choice(p) for _ in range(n))


def _null_or_raise(rules: Dict[str, Any], msg: str):
    """value_source の未解決や逆引き未ヒット時の NULL/例外処理を共通化。"""
    if bool(rules.get("allowNull", True)):
        return None
    raise ValueError(msg)


def _ref_lookup_by_label(
    table: List[Dict[str, Any]], label: Any
) -> Optional[Dict[str, Any]]:
    for r in table:
        if r.get("label") == label:
            return r
    return None


def _should_emit(rules: Dict[str, Any]) -> bool:
    """
    新仕様:
      - allowNull: True/False（デフォルト True）
      - nullProbability: 0.0..1.0（デフォルト 0.0）
      - allowNull=False のときは必ず非NULL
    """
    allow = bool(rules.get("allowNull", True))
    if not allow:
        return False

    p = float(rules.get("nullProbability", 0.0))
    if p <= 0.0:
        return False
    return random.random() < p


# ----- generator -----
def generate_data(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    # reproducible
    if spec.get("options", {}).get("reproducible", False):
        random.seed(42)

    count = int(spec.get("count", 10))
    cols = spec["columns"]
    ref_tables: Dict[str, List[Dict[str, Any]]] = spec.get("reference", {}) or {}

    # seq state
    seq_state: Dict[str, Dict[str, int]] = {}

    rows = []
    for _ in range(count):
        row: Dict[str, Any] = {}
        # REFERENCE の“暗黙ロック”はレコード単位
        chosen_ref_index: Dict[str, int] = {}

        for col_i, col in enumerate(cols):
            name = col["name"]
            rules = col.get("rules", {})

            # NULL判定
            if _should_emit(rules):
                row[name] = None
                continue

            # fixed / copy / join 最優先
            if "fixed" in rules:
                row[name] = rules["fixed"]
                continue

            if "copy" in rules:
                copy_type = rules["copy"].get("by", "")
                copy_key = rules["copy"].get("key", "")
                if copy_type == "label":
                    row[name] = row.get(copy_key)  # 参照列が無ければ None
                elif copy_type == "index":
                    try:
                        idx = int(copy_key)
                        if 0 <= idx < len(cols):
                            ref_col = cols[idx]
                            ref_name = ref_col["name"]
                            row[name] = row.get(ref_name)  # 参照列が無ければ None
                        else:
                            row[name] = _null_or_raise(
                                rules, f'copy index out of range for column "{name}"'
                            )
                    except Exception as e:
                        row[name] = _null_or_raise(
                            rules, f'copy index invalid for column "{name}": {e}'
                        )
                continue

            if "join" in rules:
                items = rules["join"]["items"]  # parse_join が必ず dict配列で返す前提
                parts = []
                for it in items:
                    if "literal" in it:
                        parts.append(it["literal"])
                    elif "reference" in it:
                        parts.append(
                            str(row.get(it["reference"], ""))
                        )  # 参照列が無ければ空
                    else:
                        raise ValueError(
                            f"join item must have 'literal' or 'reference': {it}"
                        )

                row[name] = "".join(parts)
                continue

            # ---------- REFERENCE ----------
            if "reference" in rules:
                refconf = rules["reference"] or {}
                key = refconf.get("key")
                if not key:
                    row[name] = _null_or_raise(
                        rules, f'reference key not set for column "{name}"'
                    )
                    continue
                table = ref_tables.get(key)
                if not table:
                    row[name] = _null_or_raise(
                        rules, f'reference table "{key}" not found or empty'
                    )
                    continue

                output_side = refconf.get("output", "value")  # 既定は value
                vs = refconf.get("valueSource")

                # --- 逆引き（value_source 使用時はロックしない） ---
                if isinstance(vs, dict):
                    # 1) 参照元ラベルの決定
                    label_val: Any = None
                    mode = vs.get("mode")
                    if mode == "column":
                        src_col = vs.get("col")
                        label_val = row.get(src_col)
                    elif mode == "auto":
                        # 自分より左の列から、同じ KEY かつ output=label の直近を探す
                        for j in range(col_i - 1, -1, -1):
                            prev = cols[j]
                            prev_rules = prev.get("rules", {})
                            prev_ref = prev_rules.get("reference")
                            if (
                                prev_ref
                                and prev_ref.get("key") == key
                                and prev_ref.get("output") == "label"
                            ):
                                label_val = row.get(prev["name"])
                                break
                    else:
                        # 未知モードは安全側で NULL/例外
                        row[name] = _null_or_raise(
                            rules, f'invalid value_source mode for column "{name}"'
                        )
                        continue

                    if label_val in (None, ""):
                        row[name] = _null_or_raise(
                            rules, f'value_source did not provide a label for "{name}"'
                        )
                        continue

                    rec = _ref_lookup_by_label(table, label_val)
                    if rec is None:
                        row[name] = _null_or_raise(
                            rules, f'label "{label_val}" not found in reference "{key}"'
                        )
                        continue

                    row[name] = rec.get(output_side)
                    continue

                # --- 通常参照（暗黙ロック） ---
                idx = chosen_ref_index.get(key)
                if idx is None:
                    idx = random.randrange(len(table))
                    chosen_ref_index[key] = idx
                rec = table[idx]
                row[name] = rec.get(output_side)
                continue

            # seq
            if "seq" in rules:
                st = seq_state.get(name)
                if st is None:
                    st = {"cur": rules["seq"].get("start", 1)}
                    seq_state[name] = st
                val = st["cur"]
                st["cur"] = val + int(rules["seq"].get("step", 1))
                digits = rules["seq"].get("digits")
                if digits:
                    row[name] = str(val).zfill(int(digits))
                else:
                    # digits未指定なら、string型なら文字列、数値型なら数値
                    if rules.get("type") == "string":
                        row[name] = str(val)
                    else:
                        row[name] = val
                continue

            t = rules.get("type", "string")
            # date/datetime
            if t in ("date", "datetime") or ("dateRange" in rules):
                fmt = rules.get("dateFormat")
                if not fmt:
                    # 型未指定 + dateRange だけなら既定フォーマット
                    fmt = "YYYY-MM-DD" if t != "datetime" else "YYYY-MM-DD HH:mm:ss"
                fmt_py = _to_py_dt_fmt(fmt)

                rng = rules.get("dateRange")
                if rng:
                    start = _parse_date_like(rng["start"])
                    end = _parse_date_like(rng["end"])
                else:
                    # 範囲なければ適当に直近1年
                    end = datetime.now()
                    start = end - timedelta(days=365)

                is_date_like = t == "date" or (
                    t != "datetime"
                    and rng is not None
                    and (" " not in rng["start"])
                    and (" " not in rng["end"])
                )

                if is_date_like:
                    # 日付一様
                    days = (end.date() - start.date()).days
                    off = random.randint(0, max(0, days))
                    dt = start.date() + timedelta(days=off)
                    row[name] = dt.strftime(fmt_py)
                else:
                    # datetime一様（秒）
                    start_s = int(start.timestamp())
                    end_s = int(end.timestamp())
                    if end_s < start_s:
                        start_s, end_s = end_s, start_s
                    sec = random.randint(start_s, end_s)
                    dt = datetime.fromtimestamp(sec)
                    row[name] = dt.strftime(fmt_py)
                continue

            # string
            if t == "string":
                length = int(rules.get("length", 8))
                pool = _pool_from_charset(rules.get("charset"))
                row[name] = _rand_string(length, pool)
                continue

            # int
            if t == "int":
                if "enum" in rules:
                    row[name] = random.choice(rules["enum"])
                    continue
                if "range" in rules:
                    lo, hi = rules["range"]
                    row[name] = random.randint(int(lo), int(hi))
                    continue
                row[name] = random.randint(0, 100)
                continue

            # float
            if t == "float":
                if "range" in rules:
                    lo, hi = rules["range"]
                    row[name] = round(random.uniform(float(lo), float(hi)), 6)
                    continue
                row[name] = round(random.random() * 100, 6)
                continue

            # enum（型未指定でもOK）
            if "enum" in rules:
                row[name] = random.choice(rules["enum"])
                continue

            # fallback
            row[name] = ""

        rows.append(row)
    return rows


def write_csv(
    rows: List[Dict[str, Any]],
    path: str,
    header=True,
    encoding="utf-8",
    quote_strings=True,
    quote_header=True,
):
    if not rows:
        open(path, "w").close()
        return
    fieldnames = list(rows[0].keys())

    # ヘッダ出力の扱い
    with open(path, "w", newline="", encoding=encoding) as f:
        # header
        if header:
            if quote_strings and not quote_header:
                # ヘッダは手動で非クオート
                f.write(",".join(fieldnames) + "\n")
            elif (not quote_strings) and quote_header:
                # ヘッダだけクオート
                f.write(",".join(['"{}"'.format(h) for h in fieldnames]) + "\n")
            # それ以外は writer に任せる（下で writeheader）

        # rows
        if quote_strings:
            # 全フィールドをクオート（ヘッダは上で書いた可能性あり）
            w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            if header and not (quote_strings and not quote_header):
                w.writeheader()
        else:
            w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            if header and not ((not quote_strings) and quote_header):
                w.writeheader()

        for r in rows:
            # None は空文字に
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def write_json(rows: List[Dict[str, Any]], path: str, encoding: str = "utf-8"):
    with open(path, "w", encoding=encoding) as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
