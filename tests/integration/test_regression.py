"""Regression tests: every real example invoice's full pipeline output is
checked against externally-sourced ground truth (examples/ground_truth/),
field by field.

These are the project's strongest correctness evidence -- they are not
testing this codebase's own idea of the right answer, but an independently
generated reference. A parametrized case is added here whenever a new
example invoice is added to examples/invoices/.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from invoice_intake_automation_tool import extract_invoice

INVOICE_IDS = ["0001", "0002", "0003", "0004", "0005"]


def _ground_truth(example_ground_truth_dir, invoice_id: str) -> dict:
    return json.loads((example_ground_truth_dir / f"INV-2026-{invoice_id}.json").read_text())


@pytest.fixture(params=INVOICE_IDS)
def invoice_id(request):
    return request.param


@pytest.fixture
def invoice(example_invoices_dir, invoice_id):
    return extract_invoice(example_invoices_dir / f"INV-2026-{invoice_id}.pdf")


@pytest.fixture
def gt(example_ground_truth_dir, invoice_id):
    return _ground_truth(example_ground_truth_dir, invoice_id)


class TestMoneyFieldsMatchGroundTruth:
    def test_subtotal(self, invoice, gt):
        assert str(invoice.subtotal) == gt["subtotal"]

    def test_total(self, invoice, gt):
        assert str(invoice.total) == gt["total"]

    def test_vat_amount(self, invoice, gt):
        assert str(invoice.vat_amount) == gt["vat_amount"]

    def test_vat_rate(self, invoice, gt):
        actual = str(invoice.vat_rate) if invoice.vat_rate is not None else None
        assert actual == gt["vat_rate"]

    def test_discount_amount(self, invoice, gt):
        assert str(invoice.discount_amount) == gt["discount_amount"]


class TestDatesAndIdentityMatchGroundTruth:
    def test_invoice_date(self, invoice, gt):
        assert str(invoice.invoice_date) == gt["date"]

    def test_due_date(self, invoice, gt):
        actual = str(invoice.due_date) if invoice.due_date else None
        assert actual == gt["due_date"]

    def test_vendor(self, invoice, gt):
        assert invoice.vendor == gt["vendor"]

    def test_recipient(self, invoice, gt):
        assert invoice.recipient == gt["recipient"]

    def test_vendor_country(self, invoice, gt):
        assert invoice.vendor_country == gt["vendor_country"]

    def test_recipient_country(self, invoice, gt):
        assert invoice.recipient_country == gt["recipient_country"]

    def test_currency(self, invoice, gt):
        assert invoice.currency == gt["currency"]

    def test_is_credit_note(self, invoice, gt):
        assert invoice.is_credit_note == gt["is_credit_note"]


class TestBankingAndTermsMatchGroundTruth:
    def test_bank_details(self, invoice, gt):
        assert invoice.bank_details == gt["bank_details"]

    def test_payment_terms(self, invoice, gt):
        assert invoice.payment_terms == gt["payment_terms"]


class TestConsistencyMatchesGroundTruth:
    def test_consistency_status(self, invoice, gt):
        assert invoice.consistency.value == gt["variants"]["consistency"]


class TestLineItemsMatchGroundTruth:
    def test_line_item_count(self, invoice, gt):
        assert len(invoice.line_items) == len(gt["line_items"])

    def test_line_item_fields(self, invoice, gt):
        for expected, actual in zip(gt["line_items"], invoice.line_items):
            assert actual.description == expected["description"]
            assert str(actual.unit_price) == expected["unit_price"]
            assert str(actual.amount) == expected["amount"]
            expected_rate = expected["vat_rate"]
            actual_rate = str(actual.vat_rate) if actual.vat_rate is not None else None
            assert actual_rate == expected_rate


class TestKnownConsistencyIssuesAreCorrectlyIdentified:
    """Two of the five example invoices have a deliberately incorrect
    printed total (see examples/README.md); this pins the exact ones so a
    future change that makes the consistency check too lenient (or too
    strict) is caught immediately, not just as a generic mismatch above."""

    def test_invoices_with_a_total_mismatch(self, example_invoices_dir):
        for invoice_id in ("0002", "0004"):
            invoice = extract_invoice(example_invoices_dir / f"INV-2026-{invoice_id}.pdf")
            assert invoice.consistency.value == "total_error"

    def test_invoices_that_are_internally_consistent(self, example_invoices_dir):
        for invoice_id in ("0001", "0003", "0005"):
            invoice = extract_invoice(example_invoices_dir / f"INV-2026-{invoice_id}.pdf")
            assert invoice.consistency.value == "correct"
