from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Address(BaseModel):
    """A postal address as mined from an invoice header or 'Bill to' block.

    ``postal_code`` and ``city`` are optional: the mining layer cannot
    always split a location line cleanly (see
    ``InvoiceMiner._mine_vendor_address``), and a blank string from
    extraction is normalized to ``None`` here so that "not found" is never
    confused with "confirmed empty" (see ``docs/data-model.md``).
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    street: str
    postal_code: str | None = None
    city: str | None = None
