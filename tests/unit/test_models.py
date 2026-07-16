"""Unit tests for the canonical models -- structural validation, computed
fields, and cross-field business rules.

Uses `transform_invoice(base_mined_invoice(...))` as the construction path
throughout (rather than calling `Invoice(...)` directly) since that is how
every real caller builds one, and it exercises transform.py and the model
together the same way production code does.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mined_invoices import base_mined_invoice
from pydantic import ValidationError

from invoice_intake_automation_tool.models import ConsistencyStatus
from invoice_intake_automation_tool.transform import transform_invoice


class TestRequiredFields:
    def test_missing_vendor_raises(self):
        with pytest.raises(Exception):  # TransformationError (blank) -- see transform tests for the exact type
            transform_invoice(base_mined_invoice(vendor=""))

    def test_no_line_items_raises(self):
        with pytest.raises(Exception):
            transform_invoice(base_mined_invoice(line_items=[]))


class TestDateRelationships:
    def test_due_date_before_invoice_date_raises(self):
        with pytest.raises(ValidationError, match="due_date"):
            transform_invoice(base_mined_invoice(date="2026-02-01", due_date="2026-01-01"))

    def test_due_date_equal_to_invoice_date_is_allowed(self):
        invoice = transform_invoice(base_mined_invoice(date="2026-02-01", due_date="2026-02-01"))
        assert invoice.due_date == invoice.invoice_date

    def test_missing_due_date_is_allowed(self):
        invoice = transform_invoice(base_mined_invoice(due_date=None))
        assert invoice.due_date is None


class TestNegativeAmounts:
    def test_negative_line_item_amount_rejected(self):
        with pytest.raises(ValidationError):
            transform_invoice(
                base_mined_invoice(
                    line_items=[
                        {
                            "description": "Refund",
                            "quantity": "1",
                            "unit_price": "-100.00",
                            "amount": "-100.00",
                            "vat_rate": None,
                        }
                    ]
                )
            )

    def test_negative_total_rejected_for_ordinary_invoice(self):
        # A discount larger than subtotal + VAT drives the total negative;
        # for a normal invoice that is a structural problem, not just a
        # reconciliation footnote.
        with pytest.raises(ValidationError, match="negative"):
            transform_invoice(
                base_mined_invoice(
                    discount={
                        "type": "amount",
                        "value": "5000.00",
                        "description": "large rebate",
                        "conditional": False,
                    },
                    is_credit_note=False,
                )
            )

    def test_negative_total_allowed_for_credit_note(self):
        invoice = transform_invoice(
            base_mined_invoice(
                discount={
                    "type": "amount",
                    "value": "5000.00",
                    "description": "large rebate",
                    "conditional": False,
                },
                is_credit_note=True,
            )
        )
        assert invoice.total < 0
        assert invoice.is_credit_note is True


class TestPercentageBounds:
    def test_vat_rate_over_one_hundred_percent_rejected(self):
        with pytest.raises(ValidationError):
            transform_invoice(base_mined_invoice(vat_rate="1.50"))

    def test_negative_vat_rate_rejected(self):
        with pytest.raises(ValidationError):
            transform_invoice(base_mined_invoice(vat_rate="-0.20"))


class TestCurrency:
    def test_missing_currency_is_allowed(self):
        invoice = transform_invoice(base_mined_invoice(currency=None))
        assert invoice.currency is None

    def test_non_three_letter_currency_rejected(self):
        with pytest.raises(ValidationError, match="currency"):
            transform_invoice(base_mined_invoice(currency="Euro"))


class TestSubtotalIsAlwaysDerivedFromLineItems:
    def test_subtotal_equals_sum_of_line_items(self):
        invoice = transform_invoice(
            base_mined_invoice(
                line_items=[
                    {"description": "A", "quantity": "1", "unit_price": "10.00", "amount": "10.00", "vat_rate": None},
                    {"description": "B", "quantity": "1", "unit_price": "5.00", "amount": "5.00", "vat_rate": None},
                ],
            )
        )
        assert invoice.subtotal == Decimal("15.00")

    def test_rendered_subtotal_field_does_not_affect_subtotal(self):
        # `subtotal` on the mined dict is what the page renders and may be
        # wrong; the model's `subtotal` must ignore it and use line items.
        invoice = transform_invoice(base_mined_invoice(rendered_subtotal="999999.99"))
        assert invoice.subtotal == Decimal("1000.00")
        assert invoice.rendered_subtotal == Decimal("999999.99")


class TestTotalIsDerived:
    def test_total_equals_subtotal_minus_discount_plus_vat(self):
        invoice = transform_invoice(
            base_mined_invoice(
                discount={"type": "amount", "value": "100.00", "description": "flat", "conditional": False}
            )
        )
        assert invoice.total == invoice.subtotal - invoice.discount_amount + invoice.vat_amount


class TestConsistency:
    def test_correct_when_rendered_matches_computed(self):
        invoice = transform_invoice(base_mined_invoice())
        assert invoice.consistency is ConsistencyStatus.CORRECT
        assert invoice.consistency_note is None

    def test_total_mismatch_detected(self):
        invoice = transform_invoice(base_mined_invoice(rendered_total="1300.00"))
        assert invoice.consistency is ConsistencyStatus.TOTAL_MISMATCH
        assert "total" in invoice.consistency_note.lower()

    def test_subtotal_mismatch_detected(self):
        invoice = transform_invoice(base_mined_invoice(rendered_subtotal="1005.00"))
        assert invoice.consistency is ConsistencyStatus.SUBTOTAL_MISMATCH

    def test_both_mismatched(self):
        invoice = transform_invoice(base_mined_invoice(rendered_subtotal="1005.00", rendered_total="1300.00"))
        assert invoice.consistency is ConsistencyStatus.MULTIPLE_MISMATCHES
        note = invoice.consistency_note.lower()
        assert "subtotal" in note and "total" in note

    def test_cent_level_rounding_noise_is_not_flagged(self):
        invoice = transform_invoice(base_mined_invoice(rendered_total="1200.01"))
        assert invoice.consistency is ConsistencyStatus.CORRECT


class TestImmutability:
    def test_invoice_fields_cannot_be_mutated(self):
        invoice = transform_invoice(base_mined_invoice())
        with pytest.raises(ValidationError):
            invoice.vendor = "Someone Else"

    def test_computed_fields_cannot_be_set_at_construction(self):
        # `total`/`subtotal`/`consistency` are computed fields, not
        # constructor inputs -- passing them should be rejected outright
        # rather than silently ignored.
        from invoice_intake_automation_tool.models import Address, Invoice, LineItem

        with pytest.raises(ValidationError):
            Invoice(
                invoice_id="X",
                vendor="V",
                vendor_address=Address(street="S"),
                recipient="R",
                recipient_address=Address(street="S"),
                invoice_date="2026-01-01",
                line_items=[LineItem(description="i", quantity=1, unit_price=1, amount=1)],
                vat_amount=Decimal("0"),
                discount_amount=Decimal("0"),
                rendered_subtotal=Decimal("1"),
                rendered_total=Decimal("1"),
                total=Decimal("999999"),  # not a real field -- extra="forbid" should reject it
            )
