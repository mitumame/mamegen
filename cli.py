# =========================
# mamegen/cli.py
# =========================
import sys
import pathlib
import argparse
import codecs
from .parse_block_dsl import BlockDSLParser
from .common_generator import generate_data, write_csv, write_json
from .exceptions import (
    DSLParseError,
    DSLUnexpectedTokenError,
    DSLUnknownColumnError,
    DSLInvalidRuleError,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m mamegen.cli",
        description="Generate mock data from a .mame DSL spec.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m mamegen.cli spec.mame out.csv\n"
            "  python -m mamegen.cli spec.mame out.json\n"
        ),
    )
    parser.add_argument("spec", help="Path to .mame DSL file")
    parser.add_argument("out", help="Output path (.csv or .json)")
    parser.add_argument("--version", action="version", version="mamegen 0.1.0")
    args = parser.parse_args(argv)

    spec_path = pathlib.Path(args.spec)
    out_path = pathlib.Path(args.out)

    # read spec
    try:
        dsl_text = spec_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(3)
    except OSError as e:
        print(f"Error: failed to read spec file: {spec_path} ({e})", file=sys.stderr)
        sys.exit(3)

    # parse spec
    try:
        spec = BlockDSLParser().parse(dsl_text)
    except (
        DSLParseError,
        DSLUnexpectedTokenError,
        DSLUnknownColumnError,
        DSLInvalidRuleError,
    ) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # generate rows
    rows = generate_data(spec)

    # decide format: out extension > spec CONFIG type
    fmt = (
        "JSON"
        if out_path.suffix.lower() == ".json"
        else str(spec.get("type", "CSV")).upper()
    )
    opts = spec.get("options", {})
    # 優先度: CONFIG.output_encoding > CONFIG.encoding > 'utf-8'
    enc_opt = opts.get("output_encoding") or opts.get("encoding") or "utf-8"

    try:
        enc = codecs.lookup(enc_opt).name  # 'sjis' -> 'cp932', 'UTF-8' -> 'utf-8'
    except LookupError:
        print(f"Error: unknown encoding in CONFIG: {enc_opt}", file=sys.stderr)
        sys.exit(2)

    # write
    try:
        if fmt == "JSON":
            write_json(rows, out_path.as_posix(), encoding=enc)
        else:
            write_csv(
                rows,
                out_path.as_posix(),
                header=opts.get("with_header", True),
                encoding=enc,
                quote_strings=opts.get("quote_strings", True),
                quote_header=opts.get("quote_header", True),
            )

    except OSError as e:
        print(f"Error: failed to write output: {out_path} ({e})", file=sys.stderr)
        sys.exit(3)

    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
