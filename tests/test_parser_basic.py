import pytest
from mamegen.parse_block_dsl import BlockDSLParser
from mamegen.exceptions import DSLParseError, DSLInvalidRuleError


def test_empty_input_raises():
    parser = BlockDSLParser()
    with pytest.raises(DSLParseError):
        parser.parse("")


def test_basic_config_and_header():
    dsl = """
    mamegen {
      CONFIG { type CSV }
      HEADER { ["id","name"] }
    }
    """
    spec = BlockDSLParser().parse(dsl)
    assert spec["type"] == "CSV"
    assert spec["header"] == ["id", "name"]


def test_invalid_root():
    dsl = "CONFIG { type CSV }"
    with pytest.raises(DSLInvalidRuleError):
        BlockDSLParser().parse(dsl)
