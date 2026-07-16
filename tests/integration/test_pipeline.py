"""Integration tests proving the stages compose correctly end to end:

    mined dict -> transform -> validate -> Invoice
    PDF file   -> ingest -> mine -> transform -> validate -> Invoice

Ground-truth-backed regression tests against the real example PDFs live in
test_regression.py; this file covers pipeline wiring and hand-built edge
cases that don't need a source PDF.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mined_invoices import base_mined_invoice, subtotal_mismatch_mined_invoice

from invoice_intake_automation_tool import extract_invoice, extract_invoice_batch
from invoice_intake_automation_tool.models import ConsistencyStatus
from invoice_intake_automation_tool.transform import transform_invoice


class TestMinedToInvoicePipeline:
    def test_happy_path_produces_a_validated_invoice(self):
        invoice = transform_invoice(base_mined_invoice())
        assert invoice.consistency is ConsistencyStatus.CORRECT

    def test_subtotal_mismatch_scenario(self):
        # Reconstructed from the INV-2026-0006 reference invoice, which has
        # no PDF in this repository -- see fixtures/mined_invoices.py.
        invoice = transform_invoice(subtotal_mismatch_mined_invoice())
        assert invoice.subtotal == Decimal("12918.70")
        assert invoice.total == Decimal("14856.50")
        assert invoice.consistency is ConsistencyStatus.SUBTOTAL_MISMATCH


class TestExtractInvoiceFromPdf:
    def test_extracts_a_real_example_invoice(self, example_invoices_dir):
        invoice = extract_invoice(example_invoices_dir / "INV-2026-0001.pdf")
        assert invoice.invoice_id == "INV-2026-0001"
        assert invoice.source_file == "INV-2026-0001.pdf"
        assert invoice.consistency is ConsistencyStatus.CORRECT

    def test_nonexistent_file_raises(self, example_invoices_dir):
        with pytest.raises(Exception):
            extract_invoice(example_invoices_dir / "does-not-exist.pdf")


class TestExtractInvoiceBatch:
    def test_processes_every_pdf_in_directory(self, example_invoices_dir):
        results = extract_invoice_batch(example_invoices_dir)
        assert len(results) == 5
        assert all(r.ok for r in results)

    def test_results_are_sorted_by_filename(self, example_invoices_dir):
        results = extract_invoice_batch(example_invoices_dir)
        names = [r.path.name for r in results]
        assert names == sorted(names)

    def test_pattern_filters_files(self, example_invoices_dir):
        results = extract_invoice_batch(example_invoices_dir, pattern="INV-2026-0001.pdf")
        assert len(results) == 1

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert extract_invoice_batch(tmp_path) == []

    def test_one_bad_file_does_not_abort_the_batch(self, example_invoices_dir, tmp_path):
        # Copy the real invoices plus one file that will fail ingestion,
        # and confirm the good ones still come back with a result each.
        import shutil

        for pdf in example_invoices_dir.glob("*.pdf"):
            shutil.copy(pdf, tmp_path / pdf.name)
        (tmp_path / "not-a-real-pdf.pdf").write_bytes(b"not a pdf")

        results = extract_invoice_batch(tmp_path)
        assert len(results) == 6
        ok = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        assert len(ok) == 5
        assert len(failed) == 1
        assert failed[0].path.name == "not-a-real-pdf.pdf"
