import pytest
from mamegen import parser_utils as pu
from mamegen.exceptions import DSLInvalidRuleError


def test_strip_comments():
    text = "a # comment\nb"
    out = pu.strip_comments(text)
    assert out == "a\nb"


def test_vals_in_brackets():
    s = '[1,2,"x"]'
    vals = pu.vals_in_brackets(s)
    assert vals == [1, 2, "x"]


def test_parse_int_list_error():
    with pytest.raises(DSLInvalidRuleError):
        pu.parse_int_list("a,b", 1)
