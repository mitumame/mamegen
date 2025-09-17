# =========================
# mamegen/parse_block_dsl.py
# New DSL: allow_null / null_probability (DSL keywords)
# Internal spec keys: allowNull / nullProbability (no legacy *_noNull, *_nullProbability)
# + COLUMN_RULES selectors implemented: INDEX / INDICES / LABEL / LABELS
# =========================


import re
from typing import Any, Dict, List, Tuple, Optional
from .exceptions import (
    DSLParseError,
    DSLUnexpectedTokenError,
    DSLUnknownColumnError,
    DSLInvalidRuleError,
)
from .parser_rules import RULE_TABLE
from . import parser_utils as pu


class BlockDSLParser:
    # ---------- 正規表現 ----------
    _RANGE_NUM = re.compile(r"([\-0-9\.]+)\.\.([\-0-9\.]+)")
    _RE_INT = re.compile(r"^-?\d+$")
    _RE_FLOAT = re.compile(r"^-?(?:\d+\.\d*|\d*\.\d+)$")
    # REFERENCE 行頭（ブロック開始）: REFERENCE "Q1" {
    _RE_REF_HEAD = re.compile(r"^REFERENCE\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{")

    # ---------- 公開API ----------
    def parse(self, text: str) -> Dict[str, Any]:
        """
        新DSL:
          mamegen {
            CONFIG { ... }         # type/count/encoding等
            HEADER { [ ... ] }     # 出力列（配列）
            REFERENCE {}
            CLASS  { "name" {..} } # 再利用ルール
            COLUMN_RULES { "列名" {..} ... }
          }

        NULL仕様（DSL）:
          - allow_null: true/false（デフォルト true）
          - null_probability: 0.0..1.0（デフォルト 0.0）
          - allow_null=false の場合は null_probability を無視（0.0に丸める）
        """
        raw_lines = pu.strip_comments(text).splitlines()
        # 空行を落とす（インデントは保持）
        self.lines = [ln.rstrip() for ln in raw_lines if ln.strip()]
        self.i = 0
        if not self.lines:
            raise DSLParseError(self.i + 1, "empty DSL input")

        # 既定スペック
        self.spec: Dict[str, Any] = {
            "type": "CSV",
            "count": 10,
            "options": {
                "reproducible": False,
                "with_header": True,
                "encoding": "utf-8",
                "quote_strings": True,
                "quote_header": True,
            },
            "header": [],
            "reference": {},
            "columns": [],
        }
        self.classes: Dict[str, Dict[str, Any]] = {}

        # 先頭 mamegen { ... } を読む
        self._consume_root_block()

        return self.spec

    # ---------- ルート ----------
    def _consume_root_block(self) -> None:
        # mamegen 開始
        if not self._cur().lstrip().startswith("mamegen"):
            raise DSLInvalidRuleError(self.i + 1, "root 'mamegen { ... }' is required")
        if "{" not in self._cur():
            raise DSLInvalidRuleError(self.i + 1, "expected '{' after mamegen")
        self.i += 1  # 次行へ

        section_dispatch = {
            "CONFIG": self._consume_config_block,
            "HEADER": self._consume_header_block,
            "CLASS": self._consume_class_section,
            "REFERENCE": self._consume_reference_section,
            "COLUMN_RULES": self._consume_column_rules_section,
        }

        while self.i < len(self.lines):
            L = self._cur().strip()
            if L == "}":
                self.i += 1
                break

            # Note: for-elseを意図的に避けています（可読性のため）。
            matched = False
            for key, handler in section_dispatch.items():
                if L.startswith(key):
                    handler()
                    matched = True
                    break

            if not matched:
                # 想定外トークンはスキップ
                self.i += 1

    # ---------- CONFIG ----------
    def _consume_config_block(self) -> None:
        # CONFIG { ... }
        self._expect_cur_startswith("CONFIG")
        self._expect_line_has("{")
        line = self._cur()

        def _parse_key_value(parts: list, line_no: int):
            if len(parts) < 2:
                raise DSLInvalidRuleError(
                    line_no, f"invalid CONFIG line: {' '.join(parts)}"
                )

            key, val_raw = parts[0], " ".join(parts[1:])

            # : や = を禁止
            if ":" in key or ":" in val_raw or "=" in key or "=" in val_raw:
                raise DSLInvalidRuleError(
                    line_no, "only space-separated key value is allowed (no ':' or '=')"
                )

            # 値の型推定
            if val_raw in ("true", "false"):
                val = val_raw == "true"
            elif re.fullmatch(r"-?\d+", val_raw):
                val = int(val_raw)
            else:
                val = val_raw

            if key.lower() == "type":
                self.spec["type"] = str(val).upper()
            elif key.lower() == "count":
                self.spec["count"] = int(val)
            elif key == "header":  # 後方互換
                self.spec["options"]["with_header"] = bool(val)
            else:
                self.spec["options"][key] = val

        # --- 1行完結の CONFIG に対応 ---
        inner = pu.brace_inner_or_none(line)
        if inner:
            toks = inner.split()
            if len(toks) > 2:
                raise DSLInvalidRuleError(
                    self.i + 1, "CONFIG inline must contain only one key value pair"
                )
            if toks:
                _parse_key_value(toks, self.i + 1)
            self.i += 1
            return

        # --- 複数行ブロック ---
        self.i += 1  # ブロック内へ
        while self.i < len(self.lines):
            L = self._cur().strip()

            # '}' に到達したら終了
            if L.startswith("}"):
                self.i += 1
                break

            # 行に '}' が混在する場合にも対応
            if "}" in L:
                body = L.split("}", 1)[0].strip()
                if body:
                    parts = body.split()
                    _parse_key_value(parts, self.i + 1)
                self.i += 1
                break

            parts = L.split()
            if parts:
                _parse_key_value(parts, self.i + 1)

            self.i += 1

    # ---------- HEADER ----------
    def _consume_header_block(self) -> None:
        # HEADER { [ ... ] }
        self._expect_cur_startswith("HEADER")
        self._expect_line_has("{")
        line = self._cur()

        # --- 1行完結の HEADER に対応 ---
        inner = pu.brace_inner_or_none(line)
        if inner:
            names = self._parse_header_array_text(inner)
            if not names:
                raise DSLParseError(self.i + 1, "HEADER must contain a non-empty array")
            self._set_header(names)
            self.i += 1
            return

        # --- 従来の複数行ブロック ---
        self.i += 1
        buf: List[str] = []
        bracket_open = False
        while self.i < len(self.lines):
            L = self._cur().strip()
            if "}" in L and bracket_open:
                # ']' と同じ行で '}' が来るケースもあるので、まず収集
                buf.append(L)
                names = self._parse_header_array_text("\n".join(buf))
                if not names:
                    raise DSLParseError(
                        self.i + 1, "HEADER must contain a non-empty array"
                    )
                self._set_header(names)
                self.i += 1
                break

            if L == "}":
                names = self._parse_header_array_text("\n".join(buf))
                if not names:
                    raise DSLParseError(
                        self.i + 1, "HEADER must contain a non-empty array"
                    )
                self._set_header(names)
                self.i += 1
                break

            if "[" in L or bracket_open:
                bracket_open = True
                buf.append(L)
            self.i += 1

    def _parse_header_array_text(self, text: str) -> List[str]:
        # text 内の [ ... ] を1つ抽出して pu.vals_in_brackets へ
        m = re.search(r"\[([\s\S]+)\]", text)
        if not m:
            return []
        inner = "[" + m.group(1) + "]"
        vals = pu.vals_in_brackets(inner)
        return [str(v) for v in vals]

    # ---------- REFERENCE ----------
    def _consume_reference_section(self) -> None:
        """
        REFERENCE "KEY" { "ラベル" 値 ... } を1つ以上含むセクションを読む。
        1行完結と複数行ブロックの両方に対応。
        """
        self._expect_cur_startswith("REFERENCE")
        self._expect_line_has("{")
        line = self._cur()

        # --- 1行完結: REFERENCE "Q1" { ... } ---
        inner = pu.brace_inner_or_none(line)
        mhead = self._RE_REF_HEAD.match(line.strip())
        if inner and mhead:
            key = pu.unquote(mhead.group(1))
            entries = self._parse_reference_inline(inner, self.i + 1, key)
            if not entries:
                raise DSLInvalidRuleError(self.i + 1, f'REFERENCE "{key}" is empty')
            self.spec["reference"][key] = entries
            self.i += 1
            return
        # --- 複数行ブロック: 先頭行は REFERENCE "Q1" { のみ ---
        if not mhead:
            raise DSLInvalidRuleError(self.i + 1, "invalid REFERENCE header")
        key = pu.unquote(mhead.group(1))
        self.i += 1  # 本体へ
        entries: List[Dict[str, Any]] = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            L = raw.strip()
            # 終了
            if L == "}":
                self.i += 1
                break
            # 空行はスキップ
            if not L:
                self.i += 1
                continue
            # コメントは strip_comments 済みなので基本来ないが、保険で
            if L.startswith("#"):
                self.i += 1
                continue

            try:
                lab, val = self._parse_reference_entry_line(L, self.i + 1, key)
            except DSLParseError as e:
                # 行番号は例外に含めているのでそのまま投げる
                raise e
            entries.append({"label": lab, "value": val})
            self.i += 1

        if not entries:
            raise DSLInvalidRuleError(self.i, f'REFERENCE "{key}" is empty')
        self.spec["reference"][key] = entries

    def _parse_reference_inline(
        self, inner: str, err_line: int, key: str
    ) -> List[Dict[str, Any]]:
        """
        { ... } の中身テキストを行単位で解釈して entries を返す。
        """
        entries: List[Dict[str, Any]] = []
        for off, ln in enumerate(inner.splitlines(), start=0):
            L = ln.strip()
            if not L:
                continue
            lab, val = self._parse_reference_entry_line(L, err_line + off, key)
            entries.append({"label": lab, "value": val})
        return entries

    def _parse_reference_entry_line(
        self, L: str, line_no: int, key: str
    ) -> Tuple[str, Any]:
        """
        1 行 = 1 ペア:
           "ラベル" 1
           "ラベル" -12.3
           "ラベル" "値"
        ラベルはクォート必須。値は int/float/クォート文字列のみ許可。
        """
        # 先頭のクォート文字列をラベルとして抜く
        m = re.match(r'^((?:"[^"]+")|(?:\'[^\']+\'))(.*)$', L)
        if not m:
            raise DSLParseError(
                line_no, f'REFERENCE "{key}": expected quoted label at line'
            )
        label = pu.unquote(m.group(1))
        rest = m.group(2).strip()
        if not rest:
            raise DSLParseError(line_no, f'REFERENCE "{key}": missing value token')

        # 残りの先頭トークンを値として解釈
        # まず空白で1トークン切り出し
        first = rest.split(None, 1)[0]
        # 数値?
        if self._RE_INT.fullmatch(first):
            val: Any = int(first)
            # 後続トークンは許可しない（1行1ペア）
            if rest != first:
                raise DSLParseError(
                    line_no, f'REFERENCE "{key}": extra tokens after value'
                )
            return label, val
        if self._RE_FLOAT.fullmatch(first):
            val = float(first)
            if rest != first:
                raise DSLParseError(
                    line_no, f'REFERENCE "{key}": extra tokens after value'
                )
            return label, val

        # 文字列（クォート必須）
        m2 = re.match(r'^((?:"[^"]+")|(?:\'[^\']+\'))\s*$', rest)
        if not m2:
            raise DSLParseError(
                line_no, f'REFERENCE "{key}": value must be number or quoted string'
            )
        val = pu.unquote(m2.group(1))
        return label, val

    # ---------- CLASS ----------
    def _consume_class_section(self) -> None:
        # CLASS { "name" { rules } ... }
        self._expect_cur_startswith("CLASS")
        self._expect_line_has("{")
        self.i += 1

        while self.i < len(self.lines):
            L = self._cur().strip()
            if L == "}":
                self.i += 1
                break

            # "name" { の開始
            m = re.match(r"^((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{$", L)
            if not m:
                self.i += 1
                continue
            cname = pu.unquote(m.group(1))
            self.i += 1  # ルール本体へ
            rules, self.i = self._parse_rules_block(self.i)
            self.classes[cname] = rules

    # ---------- COLUMN_RULES ----------
    def _consume_column_rules_section(self) -> None:
        # COLUMN_RULES { "列名" { rules } ... } + SELECTORS
        self._expect_cur_startswith("COLUMN_RULES")
        self._expect_line_has("{")
        line = self._cur()

        # --- 1行完結の COLUMN_RULES に対応（例: COLUMN_RULES { "x" { ... } "y" { ... } }）---
        inner = pu.brace_inner_or_none(line)
        if inner:
            # まずは従来の "name" { ... } を処理
            handled_any = False
            for col_name, inner_rules in self._iter_inline_column_blocks(inner):
                if col_name not in self.spec["header"]:
                    raise DSLUnknownColumnError(
                        self.i + 1, f'unknown column in COLUMN_RULES: "{col_name}"'
                    )
                rules = self._parse_rules_inline(inner_rules, self.i + 1)
                self._assign_rules_to_name(col_name, rules)
                handled_any = True

            # セレクタのインライン（INDEX/INDICES/LABEL/LABELS ... { ... }）も検出
            for sel_cols, inner_rules in self._iter_inline_selector_blocks(inner):
                rules = self._parse_rules_inline(inner_rules, self.i + 1)
                for nm in sel_cols:
                    self._assign_rules_to_name(nm, rules)
                handled_any = True

            if not handled_any and inner.strip():
                # 何も解釈できなかったインラインはスキップ
                pass

            self.i += 1
            return

        # --- 複数行 ---
        self.i += 1
        while self.i < len(self.lines):
            L = self._cur().strip()
            if L == "}":
                self.i += 1
                break

            # 1) "name" { ... } が同一行で閉じるパターン
            m1 = re.match(r"^((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*(.*?)\s*\}\s*$", L)
            if m1:
                col_name = pu.unquote(m1.group(1))
                if col_name not in self.spec["header"]:
                    raise DSLUnknownColumnError(
                        self.i + 1, f'unknown column in COLUMN_RULES: "{col_name}"'
                    )
                inner_rules = m1.group(2)
                rules = self._parse_rules_inline(inner_rules, self.i + 1)
                self._assign_rules_to_name(col_name, rules)
                self.i += 1
                continue

            # 2) セレクタ (INDEX/INDICES/LABEL/LABELS) の1行完結 { ... }
            sel = self._parse_selector_inline(L)
            if sel is not None:
                sel_cols, inner_rules = sel
                rules = self._parse_rules_inline(inner_rules, self.i + 1)
                for nm in sel_cols:
                    self._assign_rules_to_name(nm, rules)
                self.i += 1
                continue

            # 3) "name" { で始まり、次行以降に続くパターン
            m2 = re.match(r"^((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{$", L)
            if m2:
                col_name = pu.unquote(m2.group(1))
                if col_name not in self.spec["header"]:
                    raise DSLUnknownColumnError(
                        self.i + 1, f'unknown column in COLUMN_RULES: "{col_name}"'
                    )
                self.i += 1
                rules, self.i = self._parse_rules_block(self.i)
                self._assign_rules_to_name(col_name, rules)
                continue

            # 4) セレクタ (INDEX/INDICES/LABEL/LABELS) ブロック開始
            sel_cols = self._parse_selector_block_start(L)
            if sel_cols is not None:
                self.i += 1
                rules, self.i = self._parse_rules_block(self.i)
                for nm in sel_cols:
                    self._assign_rules_to_name(nm, rules)
                continue

            # それ以外は読み飛ばし
            self.i += 1

    # RULE_TABLE を使って 1 行を解釈し、内部 rules にマージ
    def _apply_rule_via_RULE_TABLE(
        self, rules: Dict[str, Any], raw: str, err_line: int
    ) -> bool:
        """
        1行のルール raw を RULE_TABLE で解釈し、内部 rules にマージする。
        解釈に成功したら True、対応パーサが無ければ False を返す。
        """
        # SPEC: ':' / '=' は禁止
        if (":" in raw) or ("=" in raw):
            raise DSLInvalidRuleError(err_line, "':' and '=' are not allowed")

        # 先頭トークンで RULE_TABLE を引く
        key = raw.split()[0]
        parser = RULE_TABLE.get(key)
        if not parser:
            return False

        # 解析して内部表現へマージ
        parsed = parser(raw, err_line)
        self._merge_parsed_rule_into(rules, parsed, err_line)
        return True

    # 追加: RULE_TABLE の戻り値 → 既存内部表現へのマッピング
    def _merge_parsed_rule_into(
        self, rules: Dict[str, Any], parsed: Dict[str, Any], err_line: int
    ) -> None:
        t = parsed.get("type")
        if t == "allow_null":
            rules["allowNull"] = bool(parsed["value"])
            return
        if t == "null_probability":
            rules["nullProbability"] = float(parsed["value"])
            return

        if t == "seq":
            r = rules.get("seq", {"start": 1, "step": 1, "digits": None})
            r["start"] = int(parsed["start"])
            # end は None 許容（open range）
            r["end"] = parsed.get("end")
            r["step"] = int(parsed.get("step", 1))
            rules["seq"] = r
            return
        if t == "digits":
            r = rules.get("seq", {"start": 1, "step": 1, "digits": None})
            r["digits"] = int(parsed["n"])
            rules["seq"] = r
            return
        if t == "step":
            r = rules.get("seq", {"start": 1, "step": 1, "digits": None})
            r["step"] = int(parsed["k"])
            rules["seq"] = r
            return

        if t == "charset":
            # 複数回指定で積み上げ（例: lower → number → hex）
            sets = rules.get("charset", [])
            if isinstance(sets, list):
                sets.append(parsed["name"])
            else:
                sets = [parsed["name"]]
            rules["charset"] = sets
            return
        if t == "length":
            rules["length"] = int(parsed["n"])
            # 文字列系の既定 type を立てておく（空ブロックの string/fixed 互換）
            rules.setdefault("type", "string")
            return
        if t == "regex":
            rules["type"] = "string"
            rules["regex"] = parsed["pattern"]
            return
        if t == "enum":
            rules["type"] = "int"
            rules["enum"] = parsed["values"]
            return

        # 内部的処理的な隠しルール
        if t == "fixed":
            rules["fixed"] = parsed["value"]
            # 空ブロック時の型既定と同様、type=string を立てる（互換）
            rules.setdefault("type", "string")
            return

        if t == "range":
            # 既存実装は [min, max] の配列で保持していたので合わせる
            a, b = parsed["min"], parsed["max"]
            rules["range"] = [a, b]
            if isinstance(a, int) and isinstance(b, int):
                rules["type"] = "int"
            else:
                rules["type"] = "float"
            return

        if t == "date":
            rules["type"] = "date"
            return
        if t == "datetime":
            rules["type"] = "datetime"
            return
        if t == "date_range":
            # 既存実装に合わせて type=date + dateRange{start,end}
            rules["type"] = "date"
            rules["dateRange"] = {"start": parsed["start"], "end": parsed["end"]}
            return

        if t == "copy":
            by = parsed.get("by", "label")
            rules["copy"] = {"by": by, "key": parsed["key"]}
            return

        if t == "join":
            rules["join"] = {"items": parsed["items"]}
            rules.setdefault("type", "string")
            return

        # ---------- reference family ----------
        if t == "reference":
            ref = rules.get("reference", {})
            ref["key"] = parsed["key"]
            rules["reference"] = ref
            # 既定の出力面（未指定なら value 側を既定にしても良いが、ここでは未設定のままにする）
            return
        if t == "output":
            if parsed["side"] not in ("label", "value"):
                raise DSLInvalidRuleError(err_line, "output must be label or value")
            ref = rules.get("reference", {})
            ref["output"] = parsed["side"]
            rules["reference"] = ref
            return
        if t == "value_source":
            ref = rules.get("reference", {})
            if parsed.get("auto"):
                ref["valueSource"] = {"mode": "auto"}
            else:
                ref["valueSource"] = {"mode": "column", "col": parsed["col"]}
            rules["reference"] = ref
            return

        # それ以外（未知タイプ）は将来拡張。ここではスルー。
        return

    # ---------- ルールブロック ----------
    # ブロック版: RULE_TABLEだけで処理
    def _parse_rules_block(self, i: int) -> Tuple[Dict[str, Any], int]:
        rules: Dict[str, Any] = {}
        while i < len(self.lines):
            raw = self.lines[i].strip()

            if raw == "}":
                self._ensure_empty_default(rules)
                self._finalize_null_defaults(rules, i)
                i += 1
                break

            if not raw:
                i += 1
                continue

            if raw.startswith("class "):
                cname = pu.unquote(raw.split(None, 1)[1])
                if cname in self.classes:
                    rules = self._merge_rules(rules, self.classes[cname])
                i += 1
                continue

            # RULE_TABLE で解釈（未対応はスルー）
            self._apply_rule_via_RULE_TABLE(rules, raw, i + 1)
            i += 1

        return rules, i

    # ---------- セレクタ解析ユーティリティ ----------
    def _parse_selector_inline(self, line: str) -> Optional[Tuple[List[str], str]]:
        """INDEX/LABEL/INDICES/LABELS のインライン (同一行で { ... } を閉じる) を解釈。
        戻り値: (対象列名の配列, ルール文字列) / 見つからない場合 None
        """
        # INDEX n { ... }
        m = re.match(r"^INDEX\s+(\d+)\s*\{\s*(.*?)\s*\}\s*$", line)
        if m:
            idx = int(m.group(1))
            cols = self._cols_from_single_index(idx)
            return cols, m.group(2)

        # INDICES a..b { ... }
        m = re.match(r"^INDICES\s+(\d+)\.\.(\d+)\s*\{\s*(.*?)\s*\}\s*$", line)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            cols = self._cols_from_indices_range(a, b)
            return cols, m.group(3)

        # INDICES [i1,i2,...] { ... }
        m = re.match(r"^INDICES\s*\[([^\]]+)\]\s*\{\s*(.*?)\s*\}\s*$", line)
        if m:
            arr = pu.parse_int_list(m.group(1), self.i + 1)
            cols = self._cols_from_indices_list(arr)
            return cols, m.group(2)

        # （オプション）INDICES n { ... } — 単一整数も許容
        m = re.match(r"^INDICES\s+(\d+)\s*\{\s*(.*?)\s*\}\s*$", line)
        if m:
            cols = self._cols_from_single_index(int(m.group(1)))
            return cols, m.group(2)

        # LABEL "name" { ... }
        m = re.match(
            r"^LABEL\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*(.*?)\s*\}\s*$", line
        )
        if m:
            nm = pu.unquote(m.group(1))
            cols = self._cols_from_single_label(nm)
            return cols, m.group(2)

        # LABELS ["a","b",...] { ... }
        m = re.match(r"^LABELS\s*\[([^\]]+)\]\s*\{\s*(.*?)\s*\}\s*$", line)
        if m:
            names = pu.parse_str_list(m.group(1), self.i + 1)
            cols = self._cols_from_labels_list(names)
            return cols, m.group(2)

        # LABELS "a".."b" { ... }
        m = re.match(
            r"^LABELS\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\.\.\s*((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*(.*?)\s*\}\s*$",
            line,
        )
        if m:
            a = pu.unquote(m.group(1))
            b = pu.unquote(m.group(2))
            cols = self._cols_from_labels_range(a, b)
            return cols, m.group(3)

        return None

    def _parse_selector_block_start(self, line: str) -> Optional[List[str]]:
        """INDEX/LABEL/INDICES/LABELS のブロック開始 (次行以降にルールが続く) を解釈し、
        対象列名の配列を返す。見つからない場合 None。
        例: INDEX 3 {\n ...\n}\n
        呼び出し側で self.i を 1 進め、_parse_rules_block を呼ぶ。
        """
        # INDEX n {
        m = re.match(r"^INDEX\s+(\d+)\s*\{$", line)
        if m:
            return self._cols_from_single_index(int(m.group(1)))

        # INDICES a..b {
        m = re.match(r"^INDICES\s+(\d+)\.\.(\d+)\s*\{$", line)
        if m:
            return self._cols_from_indices_range(int(m.group(1)), int(m.group(2)))

        # INDICES [i1,i2,...] {
        m = re.match(r"^INDICES\s*\[([^\]]+)\]\s*\{$", line)
        if m:
            arr = pu.parse_int_list(m.group(1), self.i + 1)
            return self._cols_from_indices_list(arr)

        # （オプション）INDICES n {
        m = re.match(r"^INDICES\s+(\d+)\s*\{$", line)
        if m:
            return self._cols_from_single_index(int(m.group(1)))

        # LABEL "name" {
        m = re.match(r"^LABEL\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{$", line)
        if m:
            nm = pu.unquote(m.group(1))
            return self._cols_from_single_label(nm)

        # LABELS ["a","b",...] {
        m = re.match(r"^LABELS\s*\[([^\]]+)\]\s*\{$", line)
        if m:
            names = pu.parse_str_list(m.group(1), self.i + 1)
            return self._cols_from_labels_list(names)

        # LABELS "a".."b" {
        m = re.match(
            r"^LABELS\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\.\.\s*((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{$",
            line,
        )
        if m:
            a = pu.unquote(m.group(1))
            b = pu.unquote(m.group(2))
            return self._cols_from_labels_range(a, b)

        return None

    def _iter_inline_selector_blocks(self, text: str):
        """COLUMN_RULES のインライン内から、
          - INDEX n { ... }
          - INDICES a..b { ... }
          - INDICES [i1,i2,...] { ... }
          - INDICES n { ... } (オプション)
          - LABEL "x" { ... }
          - LABELS ["a","b",...] { ... }
          - LABELS "a".."b" { ... }
        をすべて抽出して yield (対象列配列, ルール文字列)
        """
        patterns = [
            re.compile(r"INDEX\s+(\d+)\s*\{\s*([\s\S]*?)\s*\}"),
            re.compile(r"INDICES\s+(\d+)\.\.(\d+)\s*\{\s*([\s\S]*?)\s*\}"),
            re.compile(r"INDICES\s*\[([^\]]+)\]\s*\{\s*([\s\S]*?)\s*\}"),
            re.compile(r"INDICES\s+(\d+)\s*\{\s*([\s\S]*?)\s*\}"),
            re.compile(
                r"LABEL\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*([\s\S]*?)\s*\}"
            ),
            re.compile(r"LABELS\s*\[([^\]]+)\]\s*\{\s*([\s\S]*?)\s*\}"),
            re.compile(
                r"LABELS\s+((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\.\.\s*((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*([\s\S]*?)\s*\}"
            ),
        ]
        pos = 0
        while pos < len(text):
            matched = False
            for p in patterns:
                m = p.search(text, pos)
                if m:
                    matched = True
                    if p.pattern.startswith("INDEX"):
                        cols = self._cols_from_single_index(int(m.group(1)))
                        yield cols, m.group(2)
                        pos = m.end()
                        break
                    if "INDICES\\s+(\\d+)\\.\\.(\\d+)" in p.pattern:
                        a, b = int(m.group(1)), int(m.group(2))
                        cols = self._cols_from_indices_range(a, b)
                        yield cols, m.group(3)
                        pos = m.end()
                        break
                    if "INDICES\\s*\\[([^\\]]+)\\]" in p.pattern:
                        arr = pu.parse_int_list(m.group(1), self.i + 1)
                        cols = self._cols_from_indices_list(arr)
                        yield cols, m.group(2)
                        pos = m.end()
                        break
                    if p.pattern.startswith("INDICES\\s+(\\d+)"):
                        cols = self._cols_from_single_index(int(m.group(1)))
                        yield cols, m.group(2)
                        pos = m.end()
                        break
                    if p.pattern.startswith("LABEL\\s+"):
                        nm = pu.unquote(m.group(1))
                        cols = self._cols_from_single_label(nm)
                        yield cols, m.group(2)
                        pos = m.end()
                        break
                    if "LABELS\\s*\\[([^\\]]+)\\]" in p.pattern:
                        names = pu.parse_str_list(m.group(1), self.i + 1)
                        cols = self._cols_from_labels_list(names)
                        yield cols, m.group(2)
                        pos = m.end()
                        break
                    if (
                        r'LABELS\s+((?:"[^"]+")|(?:\'[^\']+\'))\s*\.\.' in p.pattern
                        or "LABELS" in p.pattern
                    ):
                        a = pu.unquote(m.group(1))
                        b = pu.unquote(m.group(2))
                        cols = self._cols_from_labels_range(a, b)
                        yield cols, m.group(3)
                        pos = m.end()
                        break
            if not matched:
                break

    def _set_header(self, names: List[str]) -> None:
        # 重複カラム名チェック
        seen_names = set()
        duplicates = [n for n in names if (n in seen_names) or seen_names.add(n)]
        if duplicates:
            raise DSLInvalidRuleError(
                self.i + 1, f"duplicate column names in HEADER: {', '.join(duplicates)}"
            )

        self.spec["header"] = names
        for nm in names:
            self._ensure_empty_column(nm)

    def _ensure_empty_column(self, name: str) -> None:
        if self._col_index_by_name(name) < 0:
            rules: Dict[str, Any] = {}
            self._ensure_empty_default(rules)
            self.spec["columns"].append({"name": name, "rules": rules})

    def _col_index_by_name(self, name: str) -> int:
        for idx, c in enumerate(self.spec["columns"]):
            if c["name"] == name:
                return idx
        return -1

    def _assign_rules_to_name(self, name: str, rules: Dict[str, Any]) -> None:
        self._ensure_empty_column(name)
        col_i = self._col_index_by_name(name)
        self.spec["columns"][col_i]["rules"] = rules

    @staticmethod
    def _ensure_empty_default(rules: Dict[str, Any]) -> None:
        """空ブロック時の最低限デフォルト（NULL系はここでは設定しない）"""
        if len(rules) == 0:
            rules["type"] = "string"
            rules["fixed"] = ""
        # NULLの既定は _parse_rules_block の '}' で統一的に補完する

    @staticmethod
    def _merge_rules(base: Dict[str, Any], add: Dict[str, Any]) -> Dict[str, Any]:
        """ルールの浅いマージ。後勝ち（add が base を上書き）。"""
        if not base:
            return dict(add)
        if not add:
            return dict(base)
        r = dict(base)
        r.update(add)
        return r

    # ユーティリティ（エラーメッセージ簡易）
    def _cur(self) -> str:
        return self.lines[self.i]

    def _expect_cur_startswith(self, prefix: str) -> None:
        if not self._cur().strip().startswith(prefix):
            raise DSLInvalidRuleError(self.i + 1, f"expected '{prefix}' block start")

    def _expect_line_has(self, token: str) -> None:
        if token not in self._cur():
            raise DSLUnexpectedTokenError(
                self.i + 1, f"expected '{token}' on the same line"
            )

    def _finalize_null_defaults(self, rules: Dict[str, Any], err_line: int) -> None:
        if "allowNull" not in rules:
            rules["allowNull"] = True
        if "nullProbability" not in rules:
            rules["nullProbability"] = 0.0

        # 値域チェック
        p = rules["nullProbability"]
        if not (0.0 <= p <= 1.0):
            raise DSLInvalidRuleError(
                err_line, "null_probability must be between 0 and 1"
            )

        if rules["allowNull"] is False:
            rules["nullProbability"] = 0.0

    def _iter_inline_column_blocks(self, text: str):
        """
        text 内の  "col" { ... }  をすべて (col_name, inner_rules_text) で yield
        """
        pat = re.compile(
            r"((?:\"[^\"]+\")|(?:\'[^\']+\'))\s*\{\s*([\s\S]*?)\s*\}", re.DOTALL
        )
        for m in pat.finditer(text):
            yield pu.unquote(m.group(1)), m.group(2)

    # インライン版: RULE_TABLEだけで処理
    def _parse_rules_inline(self, text: str, err_line: int) -> Dict[str, Any]:
        rules: Dict[str, Any] = {}
        segs = pu.split_inline_rules(text)

        if len(segs) > 1:
            raise DSLInvalidRuleError(
                err_line, "inline rule must contain exactly one setting"
            )

        if not segs:
            self._ensure_empty_default(rules)
            self._finalize_null_defaults(rules, err_line)
            return rules

        raw = segs[0].strip()

        if (":" in raw) or ("=" in raw):
            raise DSLInvalidRuleError(err_line, "':' and '=' are not allowed")

        if raw.startswith("class "):
            cname = pu.unquote(raw.split(None, 1)[1])
            if cname in self.classes:
                rules = self._merge_rules(rules, self.classes[cname])
        else:
            self._apply_rule_via_RULE_TABLE(rules, raw, err_line)

        if len(rules) == 0:
            self._ensure_empty_default(rules)
        self._finalize_null_defaults(rules, err_line)
        return rules

    # ---------- セレクタ -> 列名解決 ----------
    def _cols_from_single_index(self, idx: int) -> List[str]:
        if idx < 1 or idx > len(self.spec["header"]):
            raise DSLInvalidRuleError(self.i + 1, f"INDEX out of range: {idx}")
        return [self.spec["header"][idx - 1]]

    def _cols_from_indices_range(self, a: int, b: int) -> List[str]:
        if (
            a < 1
            or b < 1
            or a > len(self.spec["header"])
            or b > len(self.spec["header"])
        ):
            raise DSLInvalidRuleError(
                self.i + 1, f"INDICES range out of HEADER: {a}..{b}"
            )
        if a > b:
            raise DSLInvalidRuleError(self.i + 1, f"INDICES invalid range: {a}..{b}")
        return self.spec["header"][a - 1 : b]

    def _cols_from_indices_list(self, arr: List[int]) -> List[str]:
        cols: List[str] = []
        for v in arr:
            if v < 1 or v > len(self.spec["header"]):
                raise DSLInvalidRuleError(self.i + 1, f"INDICES item out of range: {v}")
            cols.append(self.spec["header"][v - 1])
        return cols

    def _cols_from_single_label(self, name: str) -> List[str]:
        if name not in self.spec["header"]:
            raise DSLUnknownColumnError(self.i + 1, f'unknown column label: "{name}"')
        return [name]

    def _cols_from_labels_list(self, names: List[str]) -> List[str]:
        cols: List[str] = []
        for nm in names:
            if nm not in self.spec["header"]:
                raise DSLUnknownColumnError(self.i + 1, f'unknown column label: "{nm}"')
            cols.append(nm)
        return cols

    def _cols_from_labels_range(self, a: str, b: str) -> List[str]:
        if a not in self.spec["header"] or b not in self.spec["header"]:
            missing = [x for x in [a, b] if x not in self.spec["header"]]
            raise DSLUnknownColumnError(
                self.i + 1, f'unknown column label: {", ".join(missing)}'
            )
        ai = self.spec["header"].index(a)
        bi = self.spec["header"].index(b)
        if bi < ai:
            raise DSLInvalidRuleError(self.i + 1, f'LABELS range invalid: "{a}".."{b}"')
        return self.spec["header"][ai : bi + 1]


# 関数型API


def parse_block_dsl(text: str) -> Dict[str, Any]:
    return BlockDSLParser().parse(text)
