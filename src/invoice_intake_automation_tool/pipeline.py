"""Wires the pipeline stages together into the project's small public API.

    PDF file -> ingest -> mine -> transform -> validate -> Invoice

This is the only module that needs to know about all four stages at once;
everything else (CLI, serializers, tests) should go through
:func:`extract_invoice` / :func:`extract_invoice_batch` rather than
importing the ingesting/mining internals directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pdfplumber import open as pdfopen

from .ingesting import ParagraphLayoutIngester, TableLayoutIngester
from .mining import Miner
from .models import Invoice
from .transform import transform_invoice

_table_ingester = TableLayoutIngester()
_paragraph_ingester = ParagraphLayoutIngester()
_miner = Miner()


def ingest_invoice_pdf(path: str | Path) -> dict:
    """Extract raw field content from the first page of a single-page
    invoice PDF.

    Layout is chosen per document: a page with an explicit PDF table uses
    :class:`TableLayoutIngester`; otherwise line items are read as prose
    with :class:`ParagraphLayoutIngester`. This is the same heuristic the
    project's original exploration script used, promoted to a reusable
    function -- see docs/pipeline.md for its known limitations (it cannot
    represent the "mixed" layout the source dataset itself distinguishes).

    Raises :class:`~invoice_intake_automation_tool.errors.IngestionError`
    (via the ingesters) if the PDF cannot be opened or an expected anchor
    is not found on the page.
    """
    path = Path(path)
    with pdfopen(path) as pdf:
        page = pdf.pages[0]
        if page.extract_tables():
            items = _table_ingester.extract_items(page)
            layout = "table"
        else:
            items = _paragraph_ingester.extract_items(page)
            layout = "paragraph"

        return {
            "layout": layout,
            "bill_to": _table_ingester.extract_bill_to(page),
            "header": _table_ingester.extract_header(page),
            "items": items,
            "terms": _table_ingester.extract_terms(page),
            "bank": _table_ingester.extract_bank(page),
            "total": _table_ingester.extract_rendered_total(page),
            "discount": _table_ingester.extract_discount(page),
            "subtotal": _table_ingester.extract_subtotal(page),
            "vat": _table_ingester.extract_vat(page),
        }


def extract_invoice(path: str | Path) -> Invoice:
    """Run the full pipeline on a single invoice PDF and return the
    validated, canonical :class:`Invoice`.

    This is the project's primary public entry point::

        from invoice_intake_automation_tool import extract_invoice
        invoice = extract_invoice("invoice.pdf")

    Raises ``IngestionError``, ``MiningError``, ``TransformationError``, or
    ``pydantic.ValidationError`` depending on which pipeline stage the
    document failed at (see ``errors.py`` and docs/pipeline.md).
    """
    path = Path(path)
    raw = ingest_invoice_pdf(path)
    mined = _miner.mine(raw)
    return transform_invoice(mined, source_file=path.name)


@dataclass(frozen=True)
class BatchResult:
    """The outcome of running :func:`extract_invoice` on one file within a
    batch. Exactly one of ``invoice``/``error`` is set."""

    path: Path
    invoice: Invoice | None
    error: Exception | None

    @property
    def ok(self) -> bool:
        return self.error is None


def extract_invoice_batch(directory: str | Path, *, pattern: str = "*.pdf") -> list[BatchResult]:
    """Run :func:`extract_invoice` on every matching file in ``directory``.

    A single malformed file does not abort the batch: its failure is
    captured in the returned :class:`BatchResult` alongside every other
    file's result, in sorted filename order, so a caller can report
    partial success instead of losing an entire run to one bad document.
    """
    directory = Path(directory)
    paths = sorted(directory.glob(pattern))
    results: list[BatchResult] = []
    for path in paths:
        try:
            invoice = extract_invoice(path)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: batch isolation is the point.
            # Covers every pipeline stage's exception type, including
            # pydantic.ValidationError, which is not an InvoiceToolError.
            results.append(BatchResult(path=path, invoice=None, error=exc))
        else:
            results.append(BatchResult(path=path, invoice=invoice, error=None))
    return results
