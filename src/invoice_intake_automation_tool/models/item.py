from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Item:
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    amount: Decimal