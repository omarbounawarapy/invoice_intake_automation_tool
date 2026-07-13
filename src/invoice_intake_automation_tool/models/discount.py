from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DiscountType(str, Enum):
    """How a discount's ``value`` should be interpreted.

    ``PERCENTAGE``   -- ``value`` is a fraction of the subtotal (0.02 = 2%).
    ``AMOUNT``       -- ``value`` is an absolute monetary amount.
    ``TRADE_TERMS``  -- ``value`` is a fraction, offered under early-payment
                         terms (e.g. "2/10 net 30"). Always ``conditional``.
    """

    PERCENTAGE = "percentage"
    AMOUNT = "amount"
    TRADE_TERMS = "trade_terms"


class Discount(BaseModel):
    """A discount identified on an invoice.

    ``value`` is *not* the monetary impact of the discount -- for
    percentage/trade-terms discounts it is a rate that must be applied to
    the subtotal. ``Invoice.discount_amount`` holds the actual computed
    monetary amount (0 when ``conditional`` is true), see
    ``transform.compute_discount_amount``.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    type: DiscountType
    value: Decimal = Field(ge=0)
    applied_to: str = "subtotal"
    description: str = ""
    conditional: bool = False
