from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional

from .invoice import Invoice
from .lineitem import LineItem
from .discount import Discount
from .address import Address


class InvoiceMiningError(ValueError):
    pass


class InvoiceMiner:
    """Mine normalized invoice semantics from the raw extraction produced by the ingesters.

    The extractor is intentionally dumb: it preserves text/geometry-derived strings.
    This class interprets those strings using deterministic pattern dictionaries.
    """

    # The pattern dictionaries are the main semantic rule surface.
    PATTERNS: dict[str, list[dict[str, Any]]] = {
        "vat": [
            {
                "name": "reverse_charge",
                "regex": r"reverse\s+charge\s+mechanism",
                "meta": {"vat": True, "type": "reverse_charge", "rate_source": "none"},
            },
            {
                "name": "mixed_rates",
                "regex": r"mixed\s+rates?",
                "meta": {"vat": True, "type": "mixed", "rate_source": "multiple"},
            },
            {
                "name": "included",
                "regex": r"(?:all\s+prices\s+include|subtotal\s+\(incl\.\s*vat\)|including\s+vat)",
                "meta": {"vat": True, "type": "included", "rate_source": "percentage"},
            },
            {
                "name": "percentage",
                "regex": r"(?:vat|statutory\s+vat|plus\s+\d+%\s+vat|vat\s*\(\d+(?:[.,]\d+)?%\))?.*?(?P<rate>\d+(?:[.,]\d+)?)\s*%",
                "meta": {"vat": True, "type": "percentage", "rate_source": "percentage"},
            },
            {
                "name": "applies_without_rate",
                "regex": r"(?:vat|statutory\s+vat)\s+applies",
                "meta": {"vat": True, "type": "applies", "rate_source": "unknown"},
            },
        ],
        "discount": [
            {
                "name": "early_percentage",
                "regex": r"(?:discount|less).*?(?P<rate>\d+(?:[.,]\d+)?)\s*%.*?(?:-?\s*(?:eur\s*)?(?P<amount>\d[\d'.,]*))",
                "meta": {"discount": True, "type": "percentage", "conditional": True},
            },
            {
                "name": "rebate_amount",
                "regex": r"(?:less|discount).*?(?:rebate|agreed rebate).*?(?:-\s*)?(?:eur\s*)?(?P<amount>\d[\d'.,]*)",
                "meta": {"discount": True, "type": "rebate", "conditional": False},
            },
            {
                "name": "rebate_per_agreement",
                "regex": r"less:\s*rebate\s+per\s+agreement:\s*-?\s*(?:eur\s*)?(?P<amount>\d[\d'.,]*)",
                "meta": {"discount": True, "type": "rebate", "conditional": False},
            },
            {
                "name": "generic_percentage",
                "regex": r"(?:discount|less).*?(?P<rate>\d+(?:[.,]\d+)?)\s*%",
                "meta": {"discount": True, "type": "percentage", "conditional": True},
            },
        ],
    }

    COUNTRY_FROM_IBAN = {
        "AT": "Austria",
        "DE": "Germany",
        "GB": "United Kingdom",
        "FR": "France",
        "CH": "Switzerland",
        "NL": "Netherlands",
        "NO": "Norway",
        "ES": "Spain",
        "EE": "Estonia",
    }

    COUNTRY_NAMES = tuple(COUNTRY_FROM_IBAN.values())

    def mine(self, raw: dict[str, Any]) -> Invoice:
        header = self._parse_header(raw["header"])
        bank = self._parse_bank(raw.get("bank"))
        number_format = self._detect_number_format(raw)

        line_items = [self._parse_line_item(item, number_format) for item in raw.get("items", [])]
        item_subtotal = sum((item.amount for item in line_items), Decimal("0.00"))

        vat_info = self._mine_vat(raw.get("vat", []), raw.get("subtotal", ""))
        discount_info = self._mine_discount(raw.get("discount"))

        # Canonical monetary semantics are derived from the actual line items and
        # explicit VAT/discount semantics, not blindly copied from rendered strings.
        canonical_subtotal, canonical_vat = self._canonical_tax_values(
            item_subtotal=item_subtotal,
            vat_info=vat_info,
            rendered_subtotal=raw.get("subtotal", ""),
            line_items=line_items,
        )

        discount_amount = (
            discount_info["amount"]
            if discount_info["matched"] and not discount_info["conditional"]
            else Decimal("0.00")
        )
        canonical_total = canonical_subtotal + canonical_vat - discount_amount

        rendered_subtotal = self._extract_money(raw.get("subtotal", ""), number_format)
        rendered_total = self._extract_money(raw.get("total", ""), number_format)

        consistency = self._consistency(
            canonical_subtotal=canonical_subtotal,
            canonical_vat=canonical_vat,
            canonical_total=canonical_total,
            rendered_subtotal=rendered_subtotal,
            rendered_total=rendered_total,
            discount=discount_info,
        )

        edge_case = self._edge_case(raw, vat_info, discount_info)

        return Invoice(
            invoice_id=header["invoice_id"],
            vendor_name=header["vendor_name"],
            vendor_country=self._infer_vendor_country(bank["iban"]),
            vendor_address=header["vendor_address"],
            recipient_name=raw["bill_to"][0],
            recipient_country=self._country_from_address(raw["bill_to"][-1]),
            recipient_address=self._parse_recipient_address(raw["bill_to"]),
            date=header["date"],
            due_date=header["due_date"],
            line_items=line_items,
            vat_rate=vat_info["rate"] if vat_info["type"] == "percentage" else None,
            subtotal=canonical_subtotal,
            vat_amount=canonical_vat,
            discount=discount_info["object"],
            discount_amount=discount_amount,
            total=canonical_total,
            currency=self._currency(raw),
            payment_terms=self._normalize_payment_terms(raw.get("terms", "")),
            bank_name=bank["bank_name"],
            bic=bank["bic"],
            iban=bank["iban"],
            vat_variant=vat_info["type"],
            discount_variant=discount_info["type"],
            number_format=number_format,
            layout=raw["layout"],
            consistency=consistency,
            edge_case=edge_case,
            rendered_subtotal=rendered_subtotal,
            rendered_total=rendered_total,
            error_note=self._error_note(consistency, raw, canonical_total, rendered_total),
        )

    # ------------------------------ header ------------------------------

    def _parse_header(self, header: list[str]) -> dict[str, Any]:
        invoice_match = re.search(r"(?P<vendor>.+?)\s+(?:Invoice|Credit\s+Note)\s+No:\s*(?P<id>[A-Z0-9-]+)", " ".join(header), re.I)
        if not invoice_match:
            raise InvoiceMiningError(f"Cannot parse invoice header: {header!r}")

        combined = " ".join(header)
        date_match = re.search(r"Date:\s*(?P<date>\d{1,2}\s+[A-Za-z]+\s+\d{4})", combined, re.I)
        due_match = re.search(r"Due:\s*(?P<date>\d{1,2}\s+[A-Za-z]+\s+\d{4})", combined, re.I)

        if not date_match:
            raise InvoiceMiningError(f"Invoice date missing: {header!r}")

        vendor_address = self._parse_vendor_address(header)

        return {
            "vendor_name": invoice_match.group("vendor").strip(),
            "invoice_id": invoice_match.group("id").strip(),
            "date": self._parse_date(date_match.group("date")),
            "due_date": self._parse_date(due_match.group("date")) if due_match else None,
            "vendor_address": vendor_address,
        }

    def _parse_vendor_address(self, header: list[str]) -> Address:
        # Normal invoice:
        #   header[1] = street + Date
        #   header[2] = postal/city + Due
        # Credit note extraction in the dataset has only the street/date line.
        combined = " ".join(header)
        date_pos = next((i for i, line in enumerate(header) if re.search(r"\bDate:", line, re.I)), None)
        if date_pos is None:
            raise InvoiceMiningError(f"Vendor address missing: {header!r}")

        m1 = re.search(r"^(.*?)\s+Date:\s*", header[date_pos])
        if not m1:
            raise InvoiceMiningError(f"Vendor street missing: {header!r}")
        street = m1.group(1).strip()

        due_pos = next((i for i, line in enumerate(header) if re.search(r"\bDue:", line, re.I)), None)
        if due_pos is None:
            return Address(street=street, postal_code="", city="")

        m2 = re.search(r"^(.*?)\s+Due:\s*", header[due_pos])
        if not m2:
            return Address(street=street, postal_code="", city="")
        postal, city = self._split_postal_city(m2.group(1).strip())
        return Address(street=street, postal_code=postal, city=city)

    def _parse_recipient_address(self, bill_to: list[str]) -> Address:
        if len(bill_to) < 3:
            raise InvoiceMiningError(f"Recipient address incomplete: {bill_to!r}")
        postal, city = self._split_postal_city(bill_to[2])
        return Address(street=bill_to[1], postal_code=postal, city=city)

    @staticmethod
    def _split_postal_city(value: str) -> tuple[str, str]:
        m = re.match(r"^(?P<postal>[A-Z0-9-]+)\s+(?P<city>.+)$", value.strip())
        if not m:
            raise InvoiceMiningError(f"Cannot split postal/city: {value!r}")
        return m.group("postal"), m.group("city").strip()

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value, "%d %B %Y").date()

    # ------------------------------ line items ------------------------------

    def _parse_line_item(self, raw: Any, number_format: str) -> LineItem:
        if isinstance(raw, dict):
            return LineItem(
                description=self._clean_description(raw["Description"]),
                quantity=self._parse_decimal(raw["Qty"], number_format),
                unit_price=self._parse_decimal(raw["Unit Price"], number_format),
                amount=self._parse_decimal(raw["Amount"], number_format),
            )

        if isinstance(raw, str):
            return self._parse_paragraph_item(raw, number_format)

        raise InvoiceMiningError(f"Unsupported line item type: {type(raw).__name__}")

    def _parse_paragraph_item(self, raw: str, number_format: str) -> LineItem:
        text = raw.strip()
        text = re.sub(r"^«\s*", "", text)

        # qty × unit = amount
        m = re.search(
            r"^(?P<description>.*?):\s*(?P<qty>\d+(?:[.,]\d+)?)\s*[×x]\s*(?:EUR\s*)?(?P<unit>-?[\d'.,]+)\s*(?:EUR\s*)?=\s*(?:EUR\s*)?(?P<amount>-?[\d'.,]+)\s*(?:EUR)?\.?$",
            text, re.I,
        )
        if m:
            return LineItem(
                description=self._clean_description(m.group("description")),
                quantity=self._parse_decimal(m.group("qty"), self._detect_number_format_from_number(m.group("qty"))),
                unit_price=self._parse_decimal(m.group("unit"), self._detect_number_format_from_number(m.group("unit"))),
                amount=self._parse_decimal(m.group("amount"), self._detect_number_format_from_number(m.group("amount"))),
            )

        # we invoice amount -> implicit quantity 1 and unit price = amount
        m = re.search(
            r"^(?:For\s+)?(?P<description>.*?),?\s+we\s+invoice\s+(?:EUR\s*)?(?P<amount>-?[\d'.,]+)\s*(?:EUR)?\.?$",
            text, re.I,
        )
        if m:
            amount = self._parse_decimal(m.group("amount"), self._detect_number_format_from_number(m.group("amount")))
            return LineItem(
                description=self._clean_description(m.group("description").rstrip(",")),
                quantity=Decimal("1"),
                unit_price=amount,
                amount=amount,
            )

        raise InvoiceMiningError(f"Cannot parse paragraph line item: {raw!r}")

    @staticmethod
    def _clean_description(description: str) -> str:
        # Extraction artefacts are not semantic item text.
        description = re.sub(r"\s+(?:Statutory VAT.*|Net prices\. Statutory VAT.*|All prices include .*?VAT\.|VAT reverse charge mechanism.*)$", "", description, flags=re.I)
        description = description.rstrip(" «")
        return description.strip()

    # ------------------------------ VAT ------------------------------

    def _mine_vat(self, values: list[str], subtotal_text: str) -> dict[str, Any]:
        text = " ".join([*values, subtotal_text]).strip()
        info = {"matched": False, "vat": False, "type": "none", "rate": None, "amount": Decimal("0.00"), "rates": []}

        for rule in self.PATTERNS["vat"]:
            m = re.search(rule["regex"], text, re.I)
            if not m:
                continue
            info.update(rule["meta"])
            info["matched"] = True
            if "rate" in m.groupdict() and m.group("rate"):
                info["rate"] = self._percent(m.group("rate"))
            break

        # Extract every explicit VAT rate/amount pair, especially for mixed VAT.
        for m in re.finditer(r"VAT\s*\((?P<rate>\d+(?:[.,]\d+)?)%\).*?(?P<amount>\d[\d'.,]*)\s*EUR", text, re.I):
            info["rates"].append((self._percent(m.group("rate")), self._parse_decimal(m.group("amount"), self._detect_number_format_from_number(m.group("amount")))))

        if len(info["rates"]) > 1:
            info["type"] = "mixed"
            info["rate"] = None
        else:
            generic_rate = re.search(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*%", text)
            if generic_rate:
                info["rate"] = self._percent(generic_rate.group(1))
                if info["type"] in {"none", "applies", "included"}:
                    info["type"] = "percentage" if info["type"] != "included" else "included"
            elif len(info["rates"]) == 1:
                info["rate"] = info["rates"][0][0]
                if info["type"] in {"none", "applies"}:
                    info["type"] = "percentage"

        amount_matches = re.findall(r"(?:VAT[^\d]*|VAT\s*\([^)]*\)[^\d]*)\s*(?:EUR\s*)?(?P<amount>\d[\d'.,]*)", text, re.I)
        if amount_matches:
            try:
                info["amount"] = self._parse_decimal(amount_matches[-1], self._detect_number_format_from_number(amount_matches[-1]))
            except InvoiceMiningError:
                pass

        return info

    # ------------------------------ discounts ------------------------------

    def _mine_discount(self, value: Optional[str]) -> dict[str, Any]:
        result = {
            "matched": False,
            "type": "none",
            "rate": None,
            "amount": Decimal("0.00"),
            "conditional": False,
            "object": None,
        }
        if not value:
            return result

        for rule in self.PATTERNS["discount"]:
            m = re.search(rule["regex"], value, re.I)
            if not m:
                continue
            result.update(rule["meta"])
            result["matched"] = True
            if m.groupdict().get("rate"):
                result["rate"] = self._percent(m.group("rate"))
            if m.groupdict().get("amount"):
                result["amount"] = self._parse_decimal(m.group("amount"), self._detect_number_format_from_number(m.group("amount")))
            break

        # Construct the user's Discount dataclass. Adjust field names here if its
        # definition differs; the mining semantics remain the same.
        if result["matched"]:
            result["object"] = Discount(
                type=result["type"],
                rate=result["rate"],
                amount=result["amount"],
                conditional=result["conditional"],
            )
        return result

    # ------------------------------ money / formats ------------------------------

    def _detect_number_format(self, raw: dict[str, Any]) -> str:
        samples: list[str] = []
        for item in raw.get("items", []):
            if isinstance(item, dict):
                samples.extend([item.get("Unit Price", ""), item.get("Amount", "")])
            elif isinstance(item, str):
                samples.append(item)
        samples.extend([raw.get("subtotal", ""), raw.get("total", "")])

        text = " ".join(samples)
        if re.search(r"\d'\d", text):
            return "apostrophe"
        if re.search(r"\d+\.\d{3},\d{2}\b", text):
            return "eu_dot"
        if re.search(r"\d+,\d{2}\b", text):
            return "eu_comma"
        return "us_comma"

    @staticmethod
    def _detect_number_format_from_number(value: str) -> str:
        value = value.strip()
        if "'" in value:
            return "apostrophe"
        if re.fullmatch(r"\d+\.\d{3},\d{2}", value):
            return "eu_dot"
        if re.fullmatch(r"\d+,\d{2}", value):
            return "eu_comma"
        return "us_comma"

    def _parse_decimal(self, value: str, number_format: str) -> Decimal:
        value = value.strip().replace("EUR", "").replace("€", "")
        value = value.replace(" ", "")
        value = value.rstrip(" .")
        negative = value.startswith("-")
        value = value.lstrip("+-")

        if number_format == "apostrophe":
            value = value.replace("'", "")
        elif number_format == "eu_dot":
            value = value.replace(".", "").replace(",", ".")
        elif number_format == "eu_comma":
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")

        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise InvoiceMiningError(f"Invalid decimal {value!r} from {number_format}") from exc
        return -result if negative else result

    @staticmethod
    def _percent(value: str) -> Decimal:
        value = value.replace(",", ".")
        return Decimal(value) / Decimal("100")

    def _extract_money(self, value: str, number_format: str) -> Decimal:
        matches = re.findall(r"-?\d[\d'.,]*", value)
        if not matches:
            raise InvoiceMiningError(f"No money value in {value!r}")
        return self._parse_decimal(matches[-1], self._detect_number_format_from_number(matches[-1]))

    # ------------------------------ bank / dates / country ------------------------------

    def _parse_bank(self, value: Optional[str]) -> dict[str, str]:
        if not value:
            raise InvoiceMiningError("Bank field missing")
        iban = re.search(r"IBAN:\s*([A-Z]{2}[A-Z0-9 ]+?)(?:\s*\||$)", value, re.I)
        bic = re.search(r"BIC:\s*([A-Z0-9]+)", value, re.I)
        name = re.match(r"Bank:\s*(.*?)(?:\s*\||$)", value, re.I)
        if not (iban and bic and name):
            raise InvoiceMiningError(f"Cannot parse bank field: {value!r}")
        return {"bank_name": name.group(1).strip(), "iban": re.sub(r"\s+", "", iban.group(1)).upper(), "bic": bic.group(1).strip().upper()}

    def _infer_vendor_country(self, iban: str) -> str:
        return self.COUNTRY_FROM_IBAN.get(iban[:2], "Unknown")

    def _country_from_address(self, value: str) -> str:
        for country in self.COUNTRY_NAMES:
            if country.lower() in value.lower():
                return country
        return "Unknown"

    @staticmethod
    def _currency(raw: dict[str, Any]) -> str:
        text = " ".join([raw.get("total", ""), raw.get("subtotal", "")])
        if re.search(r"\bEUR\b|€", text, re.I):
            return "EUR"
        return "UNKNOWN"

    @staticmethod
    def _normalize_payment_terms(value: str) -> str:
        return re.sub(r"^Payment terms:\s*", "", value.strip(), flags=re.I)

    # ------------------------------ canonicalization / validation ------------------------------

    def _canonical_tax_values(
        self,
        *,
        item_subtotal: Decimal,
        vat_info: dict[str, Any],
        rendered_subtotal: str,
        line_items: list[LineItem],
    ) -> tuple[Decimal, Decimal]:
        if vat_info["type"] == "reverse_charge":
            return item_subtotal, Decimal("0.00")

        if vat_info["type"] == "included":
            rate = vat_info["rate"]
            if rate is not None:
                # In this dataset the listed line-item amounts are gross when VAT is included.
                net = (item_subtotal / (Decimal("1") + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return net, item_subtotal - net

            return item_subtotal, Decimal("0.00")

        if vat_info["type"] == "mixed":
            # Exact mixed-rate decomposition is not inferable from invoice-level text alone.
            # Preserve the net item sum and use the explicit VAT amount if available.
            return item_subtotal, vat_info["amount"]

        if vat_info["rate"] is not None:
            vat = (item_subtotal * vat_info["rate"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return item_subtotal, vat

        if vat_info["amount"]:
            return item_subtotal, vat_info["amount"]

        return item_subtotal, Decimal("0.00")

    @staticmethod
    def _close(a: Decimal, b: Decimal, tolerance: Decimal = Decimal("0.02")) -> bool:
        return abs(a - b) <= tolerance

    def _consistency(self, *, canonical_subtotal: Decimal, canonical_vat: Decimal, canonical_total: Decimal,
                     rendered_subtotal: Decimal, rendered_total: Decimal, discount: dict[str, Any]) -> str:
        # Rendered subtotal may intentionally be gross or otherwise wrong; this check
        # compares against the canonical semantics rather than assuming labels are truthful.
        subtotal_ok = self._close(canonical_subtotal, rendered_subtotal)
        total_ok = self._close(canonical_total, rendered_total)
        if subtotal_ok and total_ok:
            return "correct"
        return "inconsistent"

    def _edge_case(self, raw: dict[str, Any], vat_info: dict[str, Any], discount_info: dict[str, Any]) -> str:
        flags: list[str] = []
        first_header = " ".join(raw.get("header", []))
        if "CREDIT NOTE" in first_header.upper():
            flags.append("credit_note")
        if vat_info["type"] == "mixed":
            flags.append("mixed_vat")
        if vat_info["type"] == "reverse_charge":
            flags.append("reverse_charge")
        if vat_info["type"] == "included":
            flags.append("vat_included")
        if discount_info["matched"] and discount_info["conditional"]:
            flags.append("conditional_discount")
        if any(
            isinstance(i, dict) and (
                "Statutory VAT" in str(i.get("Description", ""))
                or "Net prices" in str(i.get("Description", ""))
            )
            for i in raw.get("items", [])
        ):
            flags.append("field_bleed")
        return "+".join(flags) if flags else "none"

    @staticmethod
    def _error_note(consistency: str, raw: dict[str, Any], canonical_total: Decimal, rendered_total: Decimal) -> Optional[str]:
        if consistency == "correct":
            return None
        return f"Rendered total {rendered_total} differs from canonical total {canonical_total}; preserve rendered values separately."
