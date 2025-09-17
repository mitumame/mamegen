# mamegen/exceptions.py
class DSLParseError(Exception):
    """Base class for DSL parsing errors."""

    def __init__(self, line_no: int, message: str):
        super().__init__(f"[line {line_no}] {message}")
        self.line_no = line_no
        self.message = message


class DSLUnexpectedTokenError(DSLParseError):
    """Unexpected token or structure."""


class DSLUnknownColumnError(DSLParseError):
    """COLUMN_RULES refers to a column not present in HEADER."""


class DSLInvalidRuleError(DSLParseError):
    """Invalid or inconsistent rule specification."""
