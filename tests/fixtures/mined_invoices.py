"""Factories for hand-crafted "mined" dicts -- the shape
:meth:`InvoiceMiner.mine` produces, and :func:`transform.transform_invoice`
consumes.

Centralizing a realistic, complete base dict here keeps individual edge-case
tests short (override the one or two fields under test) instead of each
test embedding a full invoice's worth of boilerplate.
"""

from __future__ import annotations

import copy
from typing import Any


def base_mined_invoice(**overrides: Any) -> dict:
    """A complete, valid, minimal mined invoice. Tests override individual
    fields to exercise a specific transformation or validation rule."""
    data: dict[str, Any] = {
        "invoice_id": "INV-TEST-0001",
        "vendor": "Test Vendor AG",
        "vendor_country": "AT",
        "vendor_address": {"street": "Main Street 1", "postal_code": "1010", "city": "Vienna"},
        "recipient": "Test Recipient GmbH",
        "recipient_country": "DE",
        "recipient_address": {"street": "Elm Street 2", "postal_code": "80331", "city": "Munich"},
        "date": "2026-01-15",
        "due_date": "2026-02-14",
        "line_items": [
            {
                "description": "Consulting services",
                "quantity": "2",
                "unit_price": "500.00",
                "vat_rate": "0.20",
                "amount": "1000.00",
            },
        ],
        "subtotal": "1000.00",
        "vat_rate": "0.20",
        "vat_amount": "200.00",
        "discount": None,
        "discount_amount": "0.00",
        "total": "1200.00",
        "currency": "EUR",
        "payment_terms": "Net 30 days",
        "bank_details": "Test Bank | IBAN: AT000000000000000000 | BIC: TESTATWWXXX",
        "variants": {
            "vat_variant": "explicit_excluded",
            "discount_variant": "none",
            "number_format": "english",
            "layout": "table",
            "consistency": None,
            "edge_case": "none",
        },
        "rendered_subtotal": "1000.00",
        "rendered_total": "1200.00",
        "error_note": None,
        "is_credit_note": False,
    }
    data = copy.deepcopy(data)
    data.update(overrides)
    return data


def subtotal_mismatch_mined_invoice() -> dict:
    """Reconstructs the mined-data shape for the ``INV-2026-0006`` reference
    invoice (see examples/ground_truth/INV-2026-0006.json), which has no
    matching source PDF in this repository. It is the project's only
    reference example of a *subtotal* mismatch (as opposed to a *total*
    mismatch, which two of the real example PDFs already exercise), so it
    is reconstructed by hand from the published ground truth instead of
    being skipped.
    """
    return base_mined_invoice(
        invoice_id="INV-2026-0006",
        vendor="Stark Industries Europe Ltd",
        vendor_country="GB",
        vendor_address={"street": "25 Greywell Close", "postal_code": "EC2R 6AA", "city": "London"},
        recipient="Benelux Windmill Automation B.V.",
        recipient_country="NL",
        recipient_address={"street": "Walvisgracht 421", "postal_code": "1017 BP", "city": "Amsterdam"},
        date="2026-03-05",
        due_date="2026-03-05",
        line_items=[
            {
                "description": "Marketing collateral refresh",
                "quantity": "1",
                "unit_price": "5337.20",
                "vat_rate": "0.20",
                "amount": "5337.20",
            },
            {
                "description": "Board meeting facilitation",
                "quantity": "5",
                "unit_price": "1516.30",
                "vat_rate": "0.20",
                "amount": "7581.50",
            },
        ],
        subtotal="12923.70",  # as rendered on the page (true subtotal is 12918.70)
        vat_rate="0.20",
        vat_amount="2583.74",
        discount={
            "type": "percentage",
            "value": "0.05",
            "applied_to": "subtotal",
            "description": "early payment discount",
            "conditional": False,
        },
        discount_amount="645.94",
        total="14856.50",
        payment_terms="Due upon receipt",
        bank_details="Lloyds Bank | IBAN: GB01 1333 9804 2776 4157 74 | BIC: LOYDGB21XXX",
        variants={
            "vat_variant": "explicit_included",
            "discount_variant": "explicit_percentage",
            "number_format": "english",
            "layout": "table",
            "consistency": None,
            "edge_case": "none",
        },
        rendered_subtotal="12923.70",
        rendered_total="14856.50",
    )
