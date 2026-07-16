"""Command-line interface for the invoice pipeline.

    invoice-tool extract invoice.pdf
    invoice-tool extract invoice.pdf --format json
    invoice-tool extract invoice.pdf --format csv --output result.csv
    invoice-tool extract invoice.pdf --format xlsx --output result.xlsx
    invoice-tool batch ./invoices/
    invoice-tool batch ./invoices/ --format json --output batch.json

See docs/cli.md for the full command reference.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .errors import InvoiceToolError
from .models import ConsistencyStatus, Invoice
from .pipeline import BatchResult, extract_invoice, extract_invoice_batch
from .serialize import to_csv, to_json, to_text, to_xlsx

#: Exit codes. 2 is reserved by argparse itself for usage errors.
EXIT_OK = 0
EXIT_FAILURE = 1

#: Formats whose output is binary and therefore cannot be sensibly printed
#: to an interactive terminal -- see _write.
_BINARY_FORMATS = {"xlsx"}


def _stage_of(exc: BaseException) -> str:
    """Best-effort label for which pipeline stage raised ``exc``, used in
    CLI error messages (see docs/pipeline.md for the stage list)."""
    if isinstance(exc, ValidationError):
        return "validation"
    if isinstance(exc, InvoiceToolError):
        # errors.py class names are "<Stage>Error"; MiningError also
        # covers the mining module's InvoiceMiningError subclass.
        return type(exc).__name__.removesuffix("Error").lower()
    if isinstance(exc, (FileNotFoundError, IsADirectoryError, PermissionError, OSError)):
        return "input"
    return "unexpected"


def _write(content: str | bytes, output: Path | None, *, fmt: str) -> int | None:
    """Write ``content`` to ``output``, or to stdout when possible.

    Returns an exit code to short-circuit with, or ``None`` to continue
    normally. Binary formats (currently just XLSX) refuse to dump raw
    bytes onto an interactive terminal -- the same way piping the output
    of any other binary-producing CLI tool without redirecting it does not
    make sense -- but are happy to write to a redirected/piped stdout.
    """
    if output is None:
        if fmt in _BINARY_FORMATS and sys.stdout.isatty():
            print(
                f"Error (output): --format {fmt} produces binary output; "
                "use --output FILE (or redirect stdout to a file).",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        if isinstance(content, bytes):
            sys.stdout.buffer.write(content)
        else:
            sys.stdout.write(content)
            if not content.endswith("\n"):
                sys.stdout.write("\n")
    else:
        if isinstance(content, bytes):
            output.write_bytes(content)
        else:
            output.write_text(content, encoding="utf-8")
        print(f"Wrote {output}", file=sys.stderr)
    return None


def _render(invoices: Invoice | list[Invoice], fmt: str) -> str | bytes:
    if fmt == "json":
        return to_json(invoices)
    if fmt == "csv":
        return to_csv(invoices)
    if fmt == "xlsx":
        return to_xlsx(invoices)
    if isinstance(invoices, list):
        return "\n\n".join(to_text(inv) for inv in invoices)
    return to_text(invoices)


def _cmd_extract(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error (input): no such file: {path}", file=sys.stderr)
        return EXIT_FAILURE

    try:
        invoice = extract_invoice(path)
    except Exception as exc:  # noqa: BLE001 -- reported with stage context below
        print(f"Error ({_stage_of(exc)}): {exc}", file=sys.stderr)
        return EXIT_FAILURE

    early_exit = _write(_render(invoice, args.format), args.output, fmt=args.format)
    if early_exit is not None:
        return early_exit

    if args.strict and invoice.consistency is not ConsistencyStatus.CORRECT:
        return EXIT_FAILURE
    return EXIT_OK


def _summary_line(result: BatchResult) -> str:
    name = result.path.name
    if result.ok:
        status = result.invoice.consistency.value
        return f"{name:<40} {status}"
    return f"{name:<40} FAILED ({_stage_of(result.error)}): {result.error}"


def _cmd_batch(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Error (input): no such directory: {directory}", file=sys.stderr)
        return EXIT_FAILURE

    results = extract_invoice_batch(directory, pattern=args.pattern)
    if not results:
        print(f"No files matching {args.pattern!r} in {directory}", file=sys.stderr)
        return EXIT_FAILURE

    succeeded = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    flagged = [r for r in succeeded if r.invoice.consistency is not ConsistencyStatus.CORRECT]

    if args.format == "text":
        lines = [_summary_line(r) for r in results]
        lines.append("")
        lines.append(f"{len(succeeded)} processed, {len(failed)} failed")
        lines.append(f"{len(succeeded) - len(flagged)} correct, {len(flagged)} flagged for review")
        _write("\n".join(lines), args.output, fmt="text")
    else:
        invoices = [r.invoice for r in succeeded]
        early_exit = _write(_render(invoices, args.format), args.output, fmt=args.format)
        if early_exit is not None:
            return early_exit
        for r in failed:
            print(_summary_line(r), file=sys.stderr)

    if failed:
        return EXIT_FAILURE
    if args.strict and flagged:
        return EXIT_FAILURE
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-tool",
        description="Extract, normalize, and validate structured data from invoice PDFs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Process a single invoice PDF.")
    extract_parser.add_argument("path", help="Path to an invoice PDF.")
    extract_parser.add_argument(
        "--format", choices=["text", "json", "csv", "xlsx"], default="text", help="Output format (default: text)."
    )
    extract_parser.add_argument("--output", type=Path, default=None, help="Write output to this file instead of stdout.")
    extract_parser.add_argument(
        "--strict", action="store_true", help="Exit with a non-zero status if the invoice's totals do not reconcile."
    )
    extract_parser.set_defaults(func=_cmd_extract)

    batch_parser = subparsers.add_parser("batch", help="Process every invoice PDF in a directory.")
    batch_parser.add_argument("directory", help="Directory containing invoice PDFs.")
    batch_parser.add_argument(
        "--format", choices=["text", "json", "csv", "xlsx"], default="text", help="Output format (default: text summary)."
    )
    batch_parser.add_argument("--output", type=Path, default=None, help="Write output to this file instead of stdout.")
    batch_parser.add_argument("--pattern", default="*.pdf", help="Glob pattern for matching files (default: *.pdf).")
    batch_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with a non-zero status if any file fails, or any invoice's totals do not reconcile.",
    )
    batch_parser.set_defaults(func=_cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        # The consumer (e.g. `| head`) closed the pipe early. Python will
        # try to flush stdout at interpreter shutdown regardless, which
        # would raise the same error again -- redirect it to devnull first.
        import os

        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
