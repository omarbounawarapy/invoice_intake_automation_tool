"""Normalize a miner's output into the canonical :class:`Invoice` model.

This module owns *type coercion and derivation*: turning the miner's plain
strings into ``Decimal``/``date`` objects, filling in values that can be
derived from other already-mined values (an unstated VAT rate from a stated
VAT amount, for instance), and computing the monetary impact of a discount.
It does not decide whether the result is a *valid* invoice -- that is the
job of the :class:`~invoice_intake_automation_tool.models.Invoice` model's
own field constraints and validators, which run when it is constructed at
the end of :func:`transform_invoice`.

Every coercion failure raises :class:`TransformationError` with the
specific field and raw value involved, so a caller can tell a malformed
source document (a transformation failure) apart from one that is
well-formed but breaks a business rule (a
:class:`pydantic.ValidationError`, raised by the ``Invoice`` model itself).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

from .errors import TransformationError
from .models import Address, Discount, DiscountType, Invoice, LineItem

_CENT = Decimal("0.01")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace (including newlines) to a single space
    and strip the ends."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def parse_optional_str(value: Any) -> str | None:
    """Normalize a mined string field to ``None`` when it is missing or
    blank, rather than an ambiguous empty string.

    "Not found" and "confirmed empty" are different facts about a document;
    collapsing both to ``""`` would make it impossible for a caller to tell
    them apart.
    """
    if value is None:
        return None
    text = normalize_whitespace(str(value))
    return text or None


def parse_decimal(value: Any, *, field: str) -> Decimal:
    """Parse a mined numeric string into a ``Decimal``.

    The mining layer already normalizes number formats (Swiss `1'234.56`,
    German `1.234,56`, etc.) into a plain `1234.56`-style string, so this is
    usually a direct conversion; it stays defensive (and independently
    testable) rather than assuming that always holds.
    """
    if value is None or value == "":
        raise TransformationError(field, value, "value is missing")
    text = str(value).strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise TransformationError(field, value, "not a valid decimal number") from exc


def parse_date(value: Any, *, field: str) -> date:
    """Parse a mined ISO date string (`YYYY-MM-DD`) into a ``date``.

    The mining layer already rejects unparsable month names / free text
    dates before this point; this handles the remaining case of a
    syntactically plausible but calendrically impossible date (e.g.
    2026-02-30), which ``date.fromisoformat`` itself rejects.
    """
    if not value:
        raise TransformationError(field, value, "date is missing")
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TransformationError(field, value, "not a valid ISO date") from exc


def _quantize(amount: Decimal) -> Decimal:
    """Round a monetary amount to the nearest cent, half rounding up.

    Round-half-up (rather than Python's default round-half-to-even) is the
    convention used throughout ordinary invoicing; it is applied
    consistently to every computed monetary value in this module.
    """
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _clean_rate(rate: Decimal) -> Decimal:
    """Strip padded trailing zeros from a derived rate down to a floor of
    2 decimal places (20% -> ``0.20``, not ``0.2000``), while keeping extra
    precision when the rate genuinely needs it (5.5% -> ``0.055``).

    Deliberately avoids ``Decimal.normalize()``, which can switch to
    scientific notation.
    """
    text = format(rate, "f")
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0").ljust(2, "0")
    return Decimal(f"{whole}.{frac}")


def build_address(raw: Any, *, field: str) -> Address:
    if not isinstance(raw, Mapping):
        raise TransformationError(field, raw, "expected an object with street/postal_code/city")
    street = normalize_whitespace(str(raw.get("street", "")))
    if not street:
        raise TransformationError(field, raw, "missing street")
    return Address(
        street=street,
        postal_code=parse_optional_str(raw.get("postal_code")),
        city=parse_optional_str(raw.get("city")),
    )


def build_discount(raw: Any) -> Discount | None:
    """Build the descriptive :class:`Discount`, if the invoice has one.

    This does not compute the discount's monetary impact -- see
    :func:`compute_discount_amount` -- because ``Discount.value`` means
    different things per type (a rate for percentage/trade-terms, an
    absolute amount for "amount").
    """
    if not raw:
        return None
    if not isinstance(raw, Mapping):
        raise TransformationError("discount", raw, "expected an object")
    try:
        discount_type = DiscountType(raw.get("type"))
    except ValueError as exc:
        raise TransformationError("discount.type", raw.get("type"), "unrecognized discount type") from exc

    return Discount(
        type=discount_type,
        value=parse_decimal(raw.get("value"), field="discount.value"),
        applied_to=parse_optional_str(raw.get("applied_to")) or "subtotal",
        description=normalize_whitespace(str(raw.get("description", ""))),
        conditional=bool(raw.get("conditional", False)),
    )


def compute_discount_amount(discount: Discount | None, subtotal: Decimal) -> Decimal:
    """The actual monetary effect of ``discount`` on this invoice.

    A conditional discount (early-payment trade terms such as "2/10 net
    30") is not applied unless we know the customer took it, which this
    pipeline has no way to observe -- it is reported as 0.00, with the
    offer itself still visible via the ``discount`` field.
    """
    if discount is None or discount.conditional:
        return Decimal("0.00")
    if discount.type is DiscountType.AMOUNT:
        return _quantize(discount.value)
    # PERCENTAGE and TRADE_TERMS both store a rate in `value`.
    return _quantize(subtotal * discount.value)


def build_line_items(raw_items: Any, *, fallback_vat_rate: Decimal | None) -> list[LineItem]:
    if not isinstance(raw_items, list) or not raw_items:
        raise TransformationError("line_items", raw_items, "no line items found")

    items: list[LineItem] = []
    for index, raw in enumerate(raw_items):
        field = f"line_items[{index}]"
        if not isinstance(raw, Mapping):
            raise TransformationError(field, raw, "expected an object")

        description = normalize_whitespace(str(raw.get("description", "")))
        quantity = parse_decimal(raw.get("quantity"), field=f"{field}.quantity")
        unit_price = parse_decimal(raw.get("unit_price"), field=f"{field}.unit_price")
        amount = parse_decimal(raw.get("amount"), field=f"{field}.amount")

        raw_rate = raw.get("vat_rate")
        vat_rate = (
            parse_decimal(raw_rate, field=f"{field}.vat_rate")
            if raw_rate not in (None, "")
            else fallback_vat_rate
        )

        items.append(
            LineItem(
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
                vat_rate=vat_rate,
            )
        )
    return items


def derive_vat(
    *,
    rate: Decimal | None,
    amount_raw: Any,
    subtotal: Decimal,
    vat_variant: str | None,
) -> tuple[Decimal | None, Decimal]:
    """Resolve the invoice-level VAT rate and amount.

    A document usually states one of {rate, amount} explicitly and leaves
    the other implicit (see the ``implicit_no_rate`` variant in
    docs/data-model.md, where only the amount is printed). Whichever is
    missing is derived from the other and the subtotal; when *neither* is
    present, the amount is treated as zero -- correct for exempt /
    reverse-charge invoices, and otherwise surfaced for review via
    ``vat_variant`` rather than silently guessed.
    """
    amount = parse_decimal(amount_raw, field="vat_amount") if amount_raw not in (None, "") else None

    if amount is None and rate is not None:
        amount = _quantize(subtotal * rate)
    elif rate is None and amount is not None and subtotal != 0:
        rate = _clean_rate((amount / subtotal).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    elif amount is None:
        amount = Decimal("0.00")

    return rate, amount


def transform_invoice(mined: Mapping[str, Any], *, source_file: str | None = None) -> Invoice:
    """Convert a miner's output dict into a validated :class:`Invoice`.

    Raises :class:`TransformationError` if a mined value cannot be coerced
    to its canonical type, or ``pydantic.ValidationError`` if the coerced
    values violate a structural or business rule on the ``Invoice`` model
    itself (see module docstring).
    """
    variants = mined.get("variants") or {}

    invoice_id = normalize_whitespace(str(mined.get("invoice_id", "")))
    if not invoice_id:
        raise TransformationError("invoice_id", mined.get("invoice_id"), "missing invoice number")

    vendor = normalize_whitespace(str(mined.get("vendor", "")))
    recipient = normalize_whitespace(str(mined.get("recipient", "")))

    invoice_date = parse_date(mined.get("date"), field="invoice_date")
    due_date_raw = mined.get("due_date")
    due_date = parse_date(due_date_raw, field="due_date") if due_date_raw else None

    top_vat_rate_raw = mined.get("vat_rate")
    top_vat_rate = (
        parse_decimal(top_vat_rate_raw, field="vat_rate") if top_vat_rate_raw not in (None, "") else None
    )

    line_items = build_line_items(mined.get("line_items"), fallback_vat_rate=top_vat_rate)
    subtotal = sum((item.amount for item in line_items), start=Decimal("0.00"))

    vat_rate, vat_amount = derive_vat(
        rate=top_vat_rate,
        amount_raw=mined.get("vat_amount"),
        subtotal=subtotal,
        vat_variant=parse_optional_str(variants.get("vat_variant")),
    )

    if top_vat_rate is None and vat_rate is not None:
        # The invoice-level rate was only derivable *after* seeing the
        # subtotal (see derive_vat), so line items built above with no
        # stated rate of their own missed it on the first pass -- backfill
        # it now rather than leaving a rate we already know as "unknown".
        line_items = [
            item if item.vat_rate is not None else LineItem(**{**item.model_dump(), "vat_rate": vat_rate})
            for item in line_items
        ]

    discount = build_discount(mined.get("discount"))
    discount_amount = compute_discount_amount(discount, subtotal)

    rendered_subtotal = parse_decimal(
        mined.get("rendered_subtotal", mined.get("subtotal")), field="rendered_subtotal"
    )
    rendered_total = parse_decimal(mined.get("rendered_total", mined.get("total")), field="rendered_total")

    return Invoice(
        invoice_id=invoice_id,
        is_credit_note=bool(mined.get("is_credit_note", False)),
        source_file=source_file,
        vendor=vendor,
        vendor_country=parse_optional_str(mined.get("vendor_country")),
        vendor_address=build_address(mined.get("vendor_address"), field="vendor_address"),
        recipient=recipient,
        recipient_country=parse_optional_str(mined.get("recipient_country")),
        recipient_address=build_address(mined.get("recipient_address"), field="recipient_address"),
        invoice_date=invoice_date,
        due_date=due_date,
        line_items=line_items,
        currency=parse_optional_str(mined.get("currency")),
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        discount=discount,
        discount_amount=discount_amount,
        rendered_subtotal=rendered_subtotal,
        rendered_total=rendered_total,
        payment_terms=parse_optional_str(mined.get("payment_terms")),
        bank_details=parse_optional_str(mined.get("bank_details")),
        layout=parse_optional_str(variants.get("layout")),
        number_format=parse_optional_str(variants.get("number_format")),
        vat_variant=parse_optional_str(variants.get("vat_variant")),
        discount_variant=parse_optional_str(variants.get("discount_variant")),
        edge_case=parse_optional_str(variants.get("edge_case")),
    )
