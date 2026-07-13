from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .address import Address
from .discount import Discount
from .line_item import LineItem

#: Amounts within this tolerance of each other are treated as equal. This
#: absorbs cent-level rounding, not genuine discrepancies -- every mismatch
#: observed in the project's reference data (see docs/data-model.md) is at
#: least two orders of magnitude larger than this.
RECONCILIATION_TOLERANCE = Decimal("0.01")


class ConsistencyStatus(str, Enum):
    """Result of reconciling computed totals against what the document
    actually renders. This is diagnostic metadata, not a rejection: a
    mismatch means the *source document* is internally inconsistent (a
    genuine possibility for real invoices), not that extraction failed.
    """

    CORRECT = "correct"
    SUBTOTAL_MISMATCH = "subtotal_error"
    TOTAL_MISMATCH = "total_error"
    MULTIPLE_MISMATCHES = "multiple_errors"


class Invoice(BaseModel):
    """The canonical, validated representation of an invoice.

    This is the single public data contract of the project: everything
    upstream (ingestion, mining, transformation) exists to produce one of
    these, and everything downstream (serializers, CLI) exists to consume
    one.

    Design notes (see also docs/data-model.md):

    * ``subtotal``, ``total``, ``consistency`` and ``consistency_note`` are
      computed fields, not constructor inputs -- they are derived
      deterministically from ``line_items``, ``discount_amount``,
      ``vat_amount`` and the *rendered* (as-printed) figures, so it is not
      possible to construct an ``Invoice`` whose total disagrees with its
      own line items.
    * Diagnostic tags mined from free text (``vat_variant``,
      ``discount_variant``, ``layout``, ``number_format``, ``edge_case``)
      are plain strings rather than a closed enum: the mining layer's tag
      vocabulary is larger than what this repository's small fixture set
      can enumerate, and a closed enum would reject legitimate tags it
      simply hasn't seen yet.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    # -- identity ---------------------------------------------------------
    invoice_id: str = Field(min_length=1)
    is_credit_note: bool = False
    source_file: str | None = None

    # -- parties ------------------------------------------------------------
    vendor: str = Field(min_length=1)
    vendor_country: str | None = None
    vendor_address: Address
    recipient: str = Field(min_length=1)
    recipient_country: str | None = None
    recipient_address: Address

    # -- dates --------------------------------------------------------------
    invoice_date: date
    due_date: date | None = None

    # -- line items -----------------------------------------------------------
    line_items: list[LineItem] = Field(min_length=1)

    # -- money ----------------------------------------------------------------
    currency: str | None = None
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_amount: Decimal = Field(ge=0)
    discount: Discount | None = None
    discount_amount: Decimal = Field(ge=0)

    # As-rendered figures, kept for reconciliation against the computed
    # ``subtotal``/``total`` below. These come straight from the page text
    # and are not assumed correct.
    rendered_subtotal: Decimal
    rendered_total: Decimal

    # -- terms / banking --------------------------------------------------------
    payment_terms: str | None = None
    # Kept as one opaque string (bank name + IBAN + BIC) rather than split
    # fields: this mirrors what the mining layer actually publishes. The
    # mining layer *internally* parses IBAN/BIC (used to infer
    # ``vendor_country``) but does not yet expose the breakdown -- splitting
    # it out here would mean re-implementing that parsing outside the
    # mining module. See "Future improvements" in the README.
    bank_details: str | None = None

    # -- provenance / diagnostics (see docstring) --------------------------------
    layout: str | None = None
    number_format: str | None = None
    vat_variant: str | None = None
    discount_variant: str | None = None
    edge_case: str | None = None

    # -- derived fields -----------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> Decimal:
        """Sum of line-item amounts. Always internally consistent with
        ``line_items`` by construction -- it cannot be passed in and
        silently disagree with them."""
        return sum((item.amount for item in self.line_items), start=Decimal("0.00"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> Decimal:
        """``subtotal - discount_amount + vat_amount``.

        This additive relationship is the one accounting assumption this
        project makes explicit and relies on: discounts apply to the
        (VAT-exclusive) subtotal, and VAT is added on top of the
        post-discount amount. It held for every "correct" invoice in the
        project's reference dataset, including one whose document text
        described VAT as "included" (see docs/data-model.md).
        """
        return self.subtotal - self.discount_amount + self.vat_amount

    @computed_field  # type: ignore[prop-decorator]
    @property
    def consistency(self) -> ConsistencyStatus:
        subtotal_ok = abs(self.subtotal - self.rendered_subtotal) <= RECONCILIATION_TOLERANCE
        total_ok = abs(self.total - self.rendered_total) <= RECONCILIATION_TOLERANCE
        if subtotal_ok and total_ok:
            return ConsistencyStatus.CORRECT
        if not subtotal_ok and not total_ok:
            return ConsistencyStatus.MULTIPLE_MISMATCHES
        if not subtotal_ok:
            return ConsistencyStatus.SUBTOTAL_MISMATCH
        return ConsistencyStatus.TOTAL_MISMATCH

    @computed_field  # type: ignore[prop-decorator]
    @property
    def consistency_note(self) -> str | None:
        status = self.consistency
        if status is ConsistencyStatus.CORRECT:
            return None

        parts: list[str] = []
        if status in (ConsistencyStatus.SUBTOTAL_MISMATCH, ConsistencyStatus.MULTIPLE_MISMATCHES):
            parts.append(self._mismatch_sentence("subtotal", self.rendered_subtotal, self.subtotal))
        if status in (ConsistencyStatus.TOTAL_MISMATCH, ConsistencyStatus.MULTIPLE_MISMATCHES):
            parts.append(self._mismatch_sentence("total", self.rendered_total, self.total))
        return " ".join(parts)

    @staticmethod
    def _mismatch_sentence(label: str, rendered: Decimal, computed: Decimal) -> str:
        delta = rendered - computed
        sentence = (
            f"Displayed {label} {rendered} differs from computed {label} "
            f"{computed} by {delta:+}"
        )
        if computed != 0:
            pct = (delta / computed) * 100
            sentence += f" ({pct:+.2f}%)"
        return sentence + "."

    # -- cross-field validation ---------------------------------------------------

    @model_validator(mode="after")
    def _check_due_date(self) -> "Invoice":
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError(
                f"due_date ({self.due_date}) is before invoice_date ({self.invoice_date})"
            )
        return self

    @model_validator(mode="after")
    def _check_total_sign(self) -> "Invoice":
        if self.total < 0 and not self.is_credit_note:
            raise ValueError(
                f"total ({self.total}) is negative for an invoice that is "
                "not flagged as a credit note"
            )
        return self

    @model_validator(mode="after")
    def _check_currency(self) -> "Invoice":
        if self.currency is not None and not (len(self.currency) == 3 and self.currency.isalpha()):
            raise ValueError(f"currency ({self.currency!r}) is not a 3-letter code")
        return self
