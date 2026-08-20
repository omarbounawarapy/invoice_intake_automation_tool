from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LineItem(BaseModel):
    """A single invoice line.

    ``quantity`` is a ``Decimal`` rather than ``int``: the mining layer's
    number normalization preserves genuinely fractional quantities (e.g.
    "2.5 hours") while collapsing rendering artifacts like "3.00" down to
    whole numbers, so a line item is not guaranteed to be a whole count.

    ``vat_rate`` is optional at the line level: when an invoice states a
    single VAT rate for the whole document, every line inherits it; when
    the rate is genuinely mixed or entirely unstated, it is left as
    ``None`` rather than guessed (see ``docs/data-model.md``).
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
