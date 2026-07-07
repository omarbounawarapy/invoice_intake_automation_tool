from dataclasses import dataclass
from datetime import date
from decimal import Decimal


from .address import Address
from .item import Item


@dataclass
class Invoice:
    invoice_id: str
    vendor: str
    vendor_country: str
    vendor_address: Address

    recipient: str
    recipient_country: str
    recipient_address: Address

    date: date
    due_date: date

    line_items: list[Item]

    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal

    discount_amount: Decimal
    total: Decimal

    currency: str
    payment_terms: str
    bank_details: str