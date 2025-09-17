# tests/test_parser_rules.py
import pytest
from mamegen import parser_rules as pr
from mamegen.exceptions import DSLInvalidRuleError


# -------------------------
# allow_null
# -------------------------
def test_allow_null_true_false():
    assert pr.parse_allow_null("allow_null true", 1) == {
        "type": "allow_null",
        "value": True,
    }
    assert pr.parse_allow_null("allow_null false", 1) == {
        "type": "allow_null",
        "value": False,
    }


def test_allow_null_invalid():
    with pytest.raises(DSLInvalidRuleError):
        pr.parse_allow_null("allow_null maybe", 1)


# -------------------------
# null_probability
# -------------------------
def test_null_probability_ok():
    r = pr.parse_null_probability("null_probability 0.3", 1)
    assert r == {"type": "null_probability", "value": 0.3}


def test_null_probability_out_of_range():
    with pytest.raises(DSLInvalidRuleError):
        pr.parse_null_probability("null_probability 1.5", 1)


# -------------------------
# seq / digits / step
# -------------------------
def test_seq_range():
    r = pr.parse_seq("seq 1..5", 1)
    assert r["start"] == 1 and r["end"] == 5 and r["step"] == 1


def test_seq_open_range():
    r = pr.parse_seq("seq 10..", 1)
    assert r["start"] == 10 and r["end"] is None


def test_digits_ok():
    r = pr.parse_digits("digits 4", 1)
    assert r == {"type": "digits", "n": 4}


def test_step_ok():
    r = pr.parse_step("step 2", 1)
    assert r == {"type": "step", "n": 2}


# -------------------------
# charset / length
# -------------------------
def test_charset_ok():
    r = pr.parse_charset("charset lower", 1)
    assert r == {"type": "charset", "name": "lower"}


def test_charset_invalid():
    with pytest.raises(DSLInvalidRuleError):
        pr.parse_charset("charset emoji", 1)


def test_length_ok():
    r = pr.parse_length("length 8", 1)
    assert r == {"type": "length", "n": 8}


# -------------------------
# enum / fixed / copy / join
# -------------------------
def test_enum_ok():
    r = pr.parse_enum('enum ["a","b","c"]', 1)
    assert r["type"] == "enum" and len(r["values"]) == 3


def test_fixed_ok_number_and_string():
    assert pr.parse_fixed("fixed 123", 1)["value"] == 123
    assert pr.parse_fixed('fixed "hello"', 1)["value"] == "hello"


def test_copy_by_label_and_index():
    r1 = pr.parse_copy('copy "colname"', 1)
    assert r1 == {"type": "copy", "by": "label", "key": "colname"}

    r2 = pr.parse_copy("copy 2", 1)
    assert r2 == {"type": "copy", "by": "index", "key": 2}


def test_join_ok():
    r = pr.parse_join('join ["user ", user_id]', 1)
    assert r["type"] == "join"
    assert r["items"][0]["literal"] == "user "


# -------------------------
# range
# -------------------------
def test_range_int_and_float():
    r1 = pr.parse_range("range 1..10", 1)
    assert r1 == {"type": "range", "min": 1, "max": 10}

    r2 = pr.parse_range("range -1.0..1.0", 1)
    assert r2 == {"type": "range", "min": -1.0, "max": 1.0}


# -------------------------
# date / datetime
# -------------------------
def test_date_range_ok():
    r = pr.parse_date_range('date_range "2020-01-01".."2020-12-31"', 1)
    assert r["start"] == "2020-01-01" and r["end"] == "2020-12-31"


def test_date_ok():
    assert pr.parse_date("date", 1) == {"type": "date"}


def test_datetime_ok():
    assert pr.parse_datetime("datetime", 1) == {"type": "datetime"}


# -------------------------
# reference / output / value_source
# -------------------------
def test_reference_ok():
    r = pr.parse_reference('reference "Q1"', 1)
    assert r == {"type": "reference", "key": "Q1"}


def test_output_label_and_value():
    assert pr.parse_output("output label", 1) == {"type": "output", "side": "label"}
    assert pr.parse_output("output value", 1) == {"type": "output", "side": "value"}


def test_value_source_auto_and_col():
    assert pr.parse_value_source("value_source", 1) == {
        "type": "value_source",
        "auto": True,
    }
    r = pr.parse_value_source('value_source "colA"', 1)
    assert r == {"type": "value_source", "col": "colA"}
