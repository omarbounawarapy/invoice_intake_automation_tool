"""Unit tests for invoice_intake_automation_tool.transform.

Each function is tested directly against representative format variations
so a transformation bug is caught here rather than only showing up as a
mismatch in the (much coarser) regression tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mined_invoices import base_mined_invoice

from invoice_intake_automation_tool.errors import TransformationError
from invoice_intake_automation_tool.models import Address, Discount, DiscountType
from invoice_intake_automation_tool.transform import (
    build_address,
    build_discount,
    build_line_items,
    compute_discount_amount,
    derive_vat,
    normalize_whitespace,
    parse_date,
    parse_decimal,
    parse_optional_str,
    transform_invoice,
)


class TestNormalizeWhitespace:
    def test_collapses_internal_runs(self):
        assert normalize_whitespace("Acme   AG") == "Acme AG"

    def test_collapses_newlines_and_tabs(self):
        assert normalize_whitespace("Acme\n\tAG") == "Acme AG"

    def test_strips_ends(self):
        assert normalize_whitespace("  Acme AG  ") == "Acme AG"

    def test_empty_string(self):
        assert normalize_whitespace("") == ""


class TestParseOptionalStr:
    @pytest.mark.parametrize("value", [None, "", "   ", "\n\t"])
    def test_blank_becomes_none(self, value):
        assert parse_optional_str(value) is None

    def test_whitespace_is_trimmed(self):
        assert parse_optional_str("  Vienna  ") == "Vienna"

    def test_non_string_is_stringified(self):
        assert parse_optional_str(42) == "42"


class TestParseDecimal:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1234.56", Decimal("1234.56")),
            ("0.00", Decimal("0.00")),
            (" 42.00 ", Decimal("42.00")),
            ("-4204.32", Decimal("-4204.32")),
        ],
    )
    def test_valid_values(self, text, expected):
        assert parse_decimal(text, field="x") == expected

    @pytest.mark.parametrize("value", [None, "", "not-a-number", "12,34.56.78"])
    def test_invalid_values_raise(self, value):
        with pytest.raises(TransformationError) as exc_info:
            parse_decimal(value, field="amount")
        assert exc_info.value.field == "amount"


class TestParseDate:
    def test_valid_iso_date(self):
        assert str(parse_date("2026-01-15", field="invoice_date")) == "2026-01-15"

    @pytest.mark.parametrize("value", [None, "", "2026-02-30", "not-a-date", "15/01/2026"])
    def test_invalid_values_raise(self, value):
        with pytest.raises(TransformationError):
            parse_date(value, field="invoice_date")


class TestBuildAddress:
    def test_full_address(self):
        addr = build_address(
            {"street": "Main St 1", "postal_code": "1010", "city": "Vienna"}, field="vendor_address"
        )
        assert addr == Address(street="Main St 1", postal_code="1010", city="Vienna")

    def test_blank_postal_code_and_city_become_none(self):
        addr = build_address({"street": "Main St 1", "postal_code": "", "city": ""}, field="vendor_address")
        assert addr.postal_code is None
        assert addr.city is None

    def test_missing_street_raises(self):
        with pytest.raises(TransformationError):
            build_address({"postal_code": "1010", "city": "Vienna"}, field="vendor_address")

    def test_non_mapping_raises(self):
        with pytest.raises(TransformationError):
            build_address("not a dict", field="vendor_address")


class TestBuildDiscount:
    def test_none_stays_none(self):
        assert build_discount(None) is None

    def test_empty_dict_is_falsy(self):
        assert build_discount({}) is None

    def test_percentage_discount(self):
        discount = build_discount(
            {"type": "percentage", "value": "0.02", "description": "early payment", "conditional": False}
        )
        assert discount == Discount(
            type=DiscountType.PERCENTAGE, value=Decimal("0.02"), description="early payment", conditional=False
        )

    def test_unrecognized_type_raises(self):
        with pytest.raises(TransformationError):
            build_discount({"type": "buy_one_get_one", "value": "1"})


class TestComputeDiscountAmount:
    def test_no_discount(self):
        assert compute_discount_amount(None, Decimal("1000.00")) == Decimal("0.00")

    def test_conditional_discount_not_applied(self):
        discount = Discount(type=DiscountType.TRADE_TERMS, value=Decimal("0.02"), conditional=True)
        assert compute_discount_amount(discount, Decimal("1000.00")) == Decimal("0.00")

    def test_percentage_discount_applies_to_subtotal(self):
        discount = Discount(type=DiscountType.PERCENTAGE, value=Decimal("0.02"), conditional=False)
        assert compute_discount_amount(discount, Decimal("210215.90")) == Decimal("4204.32")

    def test_amount_discount_is_used_directly(self):
        discount = Discount(type=DiscountType.AMOUNT, value=Decimal("1812.10"), conditional=False)
        assert compute_discount_amount(discount, Decimal("60403.40")) == Decimal("1812.10")


class TestDeriveVat:
    def test_both_stated(self):
        rate, amount = derive_vat(
            rate=Decimal("0.20"), amount_raw="200.00", subtotal=Decimal("1000.00"), vat_variant="explicit_excluded"
        )
        assert (rate, amount) == (Decimal("0.20"), Decimal("200.00"))

    def test_amount_derived_from_rate(self):
        rate, amount = derive_vat(
            rate=Decimal("0.20"), amount_raw=None, subtotal=Decimal("1000.00"), vat_variant="explicit_excluded"
        )
        assert (rate, amount) == (Decimal("0.20"), Decimal("200.00"))

    def test_rate_derived_from_amount(self):
        # The "implicit_no_rate" case: a document states the VAT amount
        # but never prints a rate (see docs/data-model.md).
        rate, amount = derive_vat(
            rate=None, amount_raw="31070.14", subtotal=Decimal("155350.70"), vat_variant="implicit_no_rate"
        )
        assert rate == Decimal("0.20")
        assert amount == Decimal("31070.14")

    def test_neither_present_defaults_to_zero(self):
        rate, amount = derive_vat(rate=None, amount_raw=None, subtotal=Decimal("1000.00"), vat_variant=None)
        assert (rate, amount) == (None, Decimal("0.00"))

    def test_zero_subtotal_cannot_derive_rate(self):
        rate, amount = derive_vat(
            rate=None, amount_raw="0.00", subtotal=Decimal("0.00"), vat_variant="implicit_no_rate"
        )
        assert rate is None


class TestBuildLineItems:
    def test_empty_list_raises(self):
        with pytest.raises(TransformationError):
            build_line_items([], fallback_vat_rate=None)

    def test_not_a_list_raises(self):
        with pytest.raises(TransformationError):
            build_line_items(None, fallback_vat_rate=None)

    def test_missing_field_raises(self):
        with pytest.raises(TransformationError):
            build_line_items([{"description": "Widget", "unit_price": "10.00", "amount": "10.00"}], fallback_vat_rate=None)

    def test_uses_fallback_vat_rate_when_unstated(self):
        items = build_line_items(
            [{"description": "Widget", "quantity": "1", "unit_price": "10.00", "amount": "10.00", "vat_rate": None}],
            fallback_vat_rate=Decimal("0.20"),
        )
        assert items[0].vat_rate == Decimal("0.20")

    def test_stated_vat_rate_overrides_fallback(self):
        items = build_line_items(
            [
                {
                    "description": "Widget",
                    "quantity": "1",
                    "unit_price": "10.00",
                    "amount": "10.00",
                    "vat_rate": "0.05",
                }
            ],
            fallback_vat_rate=Decimal("0.20"),
        )
        assert items[0].vat_rate == Decimal("0.05")


class TestTransformInvoiceHappyPath:
    def test_computed_fields(self):
        invoice = transform_invoice(base_mined_invoice())
        assert invoice.invoice_id == "INV-TEST-0001"
        assert invoice.subtotal == Decimal("1000.00")
        assert invoice.total == Decimal("1200.00")
        assert invoice.consistency.value == "correct"

    def test_missing_invoice_id_raises(self):
        with pytest.raises(TransformationError):
            transform_invoice(base_mined_invoice(invoice_id=""))

    def test_whitespace_is_normalized_end_to_end(self):
        invoice = transform_invoice(base_mined_invoice(vendor="  Test   Vendor\nAG  "))
        assert invoice.vendor == "Test Vendor AG"
