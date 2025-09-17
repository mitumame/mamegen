import pytest
from mamegen import parser_rules as pr
from mamegen.exceptions import DSLInvalidRuleError

# (関数, 入力, 期待値) のタプル
ok_cases = [
    (pr.parse_allow_null, "allow_null true", {"type": "allow_null", "value": True}),
    (
        pr.parse_null_probability,
        "null_probability 0.5",
        {"type": "null_probability", "value": 0.5},
    ),
    (pr.parse_seq, "seq 1..3", {"type": "seq", "start": 1, "end": 3, "step": 1}),
    (pr.parse_digits, "digits 4", {"type": "digits", "n": 4}),
    (pr.parse_fixed, 'fixed "hello"', {"type": "fixed", "value": "hello"}),
    (pr.parse_fixed, "fixed 123", {"type": "fixed", "value": 123}),
]

# (関数, 入力) のタプル
ng_cases = [
    (pr.parse_allow_null, "allow_null maybe"),
    (pr.parse_null_probability, "null_probability 2.0"),
    (pr.parse_seq, "seq abc..10"),
    (pr.parse_digits, "digits -1"),
    (pr.parse_fixed, "fixed hello"),  # クォートなし文字列はエラー
]


@pytest.mark.parametrize("func, src, expected", ok_cases)
def test_ok(func, src, expected):
    r = func(src, 1)
    # 小数などで比較しやすいように dict 同士で比較
    for k, v in expected.items():
        assert r[k] == v


@pytest.mark.parametrize("func, src", ng_cases)
def test_ng(func, src):
    with pytest.raises(DSLInvalidRuleError):
        func(src, 1)
