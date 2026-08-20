from __future__ import annotations

import re
from typing import Any, Optional

from ..errors import MiningError


class InvoiceMiningError(MiningError):
    pass


class InvoiceMiner:
    """
    Mine semantic information from the raw invoice extraction.

    Contract:
    - returns only dicts/lists/scalars
    - never constructs domain dataclasses
    - never creates Decimal/int/date objects
    - monetary values are returned as normalized strings
    - dates are returned as ISO strings
    - no arithmetic / validation / reconciliation
    """

    COUNTRY_FROM_IBAN = {
        "AT": "AT",
        "DE": "DE",
        "GB": "GB",
        "FR": "FR",
        "CH": "CH",
        "NL": "NL",
        "NO": "NO",
        "ES": "ES",
        "EE": "EE",
    }

    MONTHS = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }

    VAT_PATTERNS = {
        "reverse_charge": re.compile(r"reverse\s+charge\s+mechanism", re.I),
        "mixed": re.compile(r"mixed\s+rates?", re.I),
        "included": re.compile(
            r"all\s+prices\s+include|subtotal\s*\(\s*incl\.\s*vat\s*\)|subtotal\s+including\s+vat",
            re.I,
        ),
        "applies": re.compile(r"(?:statutory\s+)?vat\s+applies", re.I),
    }

    DISCOUNT_PATTERNS = {
        "percentage": re.compile(
            r"(?:discount|less).*?(?P<rate>\d+(?:[.,]\d+)?)\s*%",
            re.I,
        ),
        "rebate": re.compile(
            r"(?:rebate\s+per\s+agreement|agreed\s+rebate|rebate)",
            re.I,
        ),
    }

    def mine(self, raw: dict[str, Any]) -> dict[str, Any]:
        header = self._mine_header(raw.get("header", []))
        recipient = self._mine_recipient(raw.get("bill_to", []))
        bank = self._mine_bank(raw.get("bank"))

        vat = self._mine_vat(raw.get("vat", []), raw.get("subtotal", ""))
        discount = self._mine_discount(raw.get("discount"), raw.get("terms", ""))

        line_items = [
            self._mine_line_item(item, vat["rate"])
            for item in raw.get("items", [])
        ]

        number_format = self._detect_number_format(raw)
        rendered_subtotal = self._extract_money_string(raw.get("subtotal", ""), number_format)
        rendered_total = self._extract_money_string(raw.get("total", ""), number_format)

        return {
            "invoice_id": header["invoice_id"],
            "vendor": header["vendor"],
            "vendor_country": bank["country"],
            "vendor_address": header["vendor_address"],
            "recipient": recipient["recipient"],
            "recipient_country": recipient["recipient_country"],
            "recipient_address": recipient["recipient_address"],
            "date": header["date"],
            "due_date": header["due_date"],
            "line_items": line_items,
            "subtotal": rendered_subtotal,
            "vat_rate": vat["rate"],
            "vat_amount": vat["amount"],
            "discount": discount,
            "discount_amount": self._mine_discount_amount(raw.get("discount"), number_format, discount),
            "total": rendered_total,
            "currency": self._mine_currency(raw),
            "payment_terms": self._mine_payment_terms(raw.get("terms")),
            "bank_details": self._mine_bank_details(raw.get("bank")),
            "variants": {
                "vat_variant": vat["variant"],
                "discount_variant": discount["type"] if discount else "none",
                "number_format": number_format,
                "layout": raw.get("layout"),
                # Deliberately not validated here.
                "consistency": None,
                "edge_case": self._mine_edge_case(raw, vat, discount),
            },
            "rendered_subtotal": rendered_subtotal,
            "rendered_total": rendered_total,
            "error_note": None,
            "is_credit_note": self._is_credit_note(raw.get("header", [])),
        }

    # ------------------------------------------------------------------
    # Header / address
    # ------------------------------------------------------------------

    def _mine_header(self, header: list[str]) -> dict[str, Any]:
        combined = " ".join(header)
        is_credit_note = self._is_credit_note(header)

        pattern = (
            r"(?:CREDIT\s+NOTE\s+)?"
            r"(?P<vendor>.+?)\s+"
            r"(?:Invoice|Credit\s+Note)\s+No:\s*"
            r"(?P<invoice_id>[A-Z0-9-]+)"
        )
        match = re.search(pattern, combined, re.I)
        if not match:
            raise InvoiceMiningError(f"Cannot mine invoice header: {header!r}")

        vendor = match.group("vendor").strip()
        vendor = re.sub(r"^CREDIT\s+NOTE\s+", "", vendor, flags=re.I).strip()

        date_match = re.search(r"Date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", combined, re.I)
        due_match = re.search(r"Due:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", combined, re.I)

        if not date_match:
            raise InvoiceMiningError(f"Date missing from header: {header!r}")

        return {
            "invoice_id": match.group("invoice_id").strip(),
            "vendor": vendor,
            "date": self._date_string(date_match.group(1)),
            "due_date": self._date_string(due_match.group(1)) if due_match else None,
            "vendor_address": self._mine_vendor_address(header),
        }

    def _mine_vendor_address(self, header: list[str]) -> dict[str, str]:
        date_index = next(
            (i for i, line in enumerate(header) if re.search(r"\bDate:", line, re.I)),
            None,
        )
        if date_index is None:
            raise InvoiceMiningError(f"Vendor address missing: {header!r}")

        street_match = re.search(r"^(.*?)\s+Date:", header[date_index], re.I)
        if not street_match:
            raise InvoiceMiningError(f"Vendor street missing: {header!r}")

        street = street_match.group(1).strip()

        due_index = next(
            (i for i, line in enumerate(header) if re.search(r"\bDue:", line, re.I)),
            None,
        )
        if due_index is None:
            return {"street": street, "postal_code": "", "city": ""}

        location_match = re.search(r"^(.*?)\s+Due:", header[due_index], re.I)
        if not location_match:
            return {"street": street, "postal_code": "", "city": ""}

        postal, city = self._split_postal_city(location_match.group(1).strip())
        return {"street": street, "postal_code": postal, "city": city}

    def _mine_recipient(self, bill_to: list[str]) -> dict[str, Any]:
        if len(bill_to) < 3:
            raise InvoiceMiningError(f"Recipient address incomplete: {bill_to!r}")

        postal, city_country = self._split_postal_city(bill_to[2])
        city, country = self._split_city_country(city_country)

        return {
            "recipient": bill_to[0].strip(),
            "recipient_country": self._country_code(country),
            "recipient_address": {
                "street": bill_to[1].strip(),
                "postal_code": postal,
                "city": city,
            },
        }

    @staticmethod
    def _split_postal_city(value: str) -> tuple[str, str]:
        value = value.strip()

        # UK: EC2R 6AA London
        uk = re.match(r"^(?P<postal>[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s+(?P<city>.+)$", value, re.I)
        if uk:
            return uk.group("postal").upper(), uk.group("city").strip()

        # NL: 1017 BP Amsterdam
        nl = re.match(r"^(?P<postal>\d{4}\s+[A-Z]{2})\s+(?P<city>.+)$", value, re.I)
        if nl:
            return nl.group("postal").upper(), nl.group("city").strip()

        # Generic numeric/postal token.
        generic = re.match(r"^(?P<postal>[A-Z0-9-]+)\s+(?P<city>.+)$", value)
        if generic:
            return generic.group("postal"), generic.group("city").strip()

        raise InvoiceMiningError(f"Cannot split postal/city: {value!r}")

    @staticmethod
    def _split_city_country(value: str) -> tuple[str, str]:
        if "," not in value:
            return value.strip(), ""
        city, country = value.rsplit(",", 1)
        return city.strip(), country.strip()

    def _country_code(self, country_name: str) -> Optional[str]:
        normalized = country_name.strip().lower()
        mapping = {
            "austria": "AT",
            "germany": "DE",
            "united kingdom": "GB",
            "france": "FR",
            "switzerland": "CH",
            "netherlands": "NL",
            "norway": "NO",
            "spain": "ES",
            "estonia": "EE",
        }
        return mapping.get(normalized)

    @staticmethod
    def _date_string(value: str) -> str:
        match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", value.strip())
        if not match:
            raise InvoiceMiningError(f"Invalid date text: {value!r}")
        day = int(match.group(1))
        month = InvoiceMiner.MONTHS.get(match.group(2).lower())
        if not month:
            raise InvoiceMiningError(f"Unknown month: {value!r}")
        return f"{match.group(3)}-{month}-{day:02d}"

    # ------------------------------------------------------------------
    # Line items
    # ------------------------------------------------------------------

    def _mine_line_item(self, raw: Any, invoice_vat_rate: Optional[str]) -> dict[str, str]:
        if isinstance(raw, dict):
            description = self._clean_description(str(raw.get("Description", "")))
            return {
                "description": description,
                "quantity": self._normalize_quantity(str(raw.get("Qty", ""))),
                "unit_price": self._normalize_number(str(raw.get("Unit Price", ""))),
                "vat_rate": invoice_vat_rate,
                "amount": self._normalize_number(str(raw.get("Amount", ""))),
            }

        if isinstance(raw, str):
            result = self._mine_paragraph_item(raw)
            result["vat_rate"] = invoice_vat_rate
            return result

        raise InvoiceMiningError(f"Unsupported line item: {raw!r}")

    def _mine_paragraph_item(self, raw: str) -> dict[str, str]:
        text = re.sub(r"^«\s*", "", raw.strip())

        # description: qty × unit = amount
        match = re.search(
            r"^(?P<description>.*?):\s*"
            r"(?P<quantity>\d+(?:[.,]\d+)?)\s*[×x]\s*"
            r"(?:EUR\s*)?(?P<unit>-?[\d'.,]+)\s*"
            r"(?:EUR\s*)?=\s*(?:EUR\s*)?(?P<amount>-?[\d'.,]+)\s*(?:EUR)?\.?$",
            text,
            re.I,
        )
        if match:
            return {
                "description": self._clean_description(match.group("description")),
                "quantity": self._normalize_quantity(match.group("quantity")),
                "unit_price": self._normalize_number(match.group("unit")),
                "amount": self._normalize_number(match.group("amount")),
            }

        # For description, we invoice amount.
        match = re.search(
            r"^(?:For\s+)?(?P<description>.*?),?\s+we\s+invoice\s+"
            r"(?:EUR\s*)?(?P<amount>-?[\d'.,]+)\s*(?:EUR)?\.?$",
            text,
            re.I,
        )
        if match:
            return {
                "description": self._clean_description(match.group("description").rstrip(",")),
                "amount": self._normalize_number(match.group("amount")),
            }

        raise InvoiceMiningError(f"Cannot mine paragraph line item: {raw!r}")

    # ------------------------------------------------------------------
    # VAT
    # ------------------------------------------------------------------

    def _mine_vat(self, values: list[str], subtotal: str) -> dict[str, Any]:
        text = " ".join(str(v) for v in values if v)
        rates = self._extract_percentages(text)
        amounts = self._extract_vat_amounts(text)

        if self.VAT_PATTERNS["reverse_charge"].search(text):
            variant = "reverse_charge"
        elif self.VAT_PATTERNS["mixed"].search(text) or len(set(rates)) > 1:
            variant = "mixed"
        elif self.VAT_PATTERNS["included"].search(text):
            variant = "included"
        elif rates:
            variant = "explicit_excluded"
        elif self.VAT_PATTERNS["applies"].search(text):
            variant = "applies"
        elif amounts:
            variant = "explicit_excluded"
        else:
            variant = "none"

        rate = rates[0] if len(set(rates)) == 1 and variant != "mixed" else None
        amount = amounts[0] if len(amounts) == 1 else None

        return {
            "variant": variant,
            "rate": rate,
            "rates": self._unique(rates),
            "amount": amount,
            "amounts": self._unique(amounts),
        }

    @staticmethod
    def _extract_percentages(text: str) -> list[str]:
        matches = re.findall(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*%", text)
        return [InvoiceMiner._normalize_percent(x) for x in matches]

    def _extract_vat_amounts(self, text: str) -> list[str]:
        patterns = [
            r"VAT\s*\([^)]*\)\s*:\s*(?:EUR\s*)?(?P<amount>-?[\d'.,]+)",
            r"VAT\s*:\s*(?:EUR\s*)?(?P<amount>-?[\d'.,]+)",
            r"amounting\s+to\s+(?:EUR\s*)?(?P<amount>-?[\d'.,]+)",
            r"statutory\s+VAT\s+of\s+(?:EUR\s*)?(?P<amount>-?[\d'.,]+)",
            r"statutory\s+VAT\s*\([^)]*\)\s+applies:\s*(?:EUR\s*)?(?P<amount>-?[\d'.,]+)",
        ]
        found: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.I):
                found.append(self._normalize_number(match.group("amount")))
        return self._unique(found)

    @staticmethod
    def _normalize_percent(value: str) -> str:
        # Canonical percentage as a string: 20% -> "0.20", 2% -> "0.02".
        value = value.strip().replace(",", ".")
        if "." in value:
            whole, fraction = value.split(".", 1)
            fraction = fraction.rstrip("0")
        else:
            whole, fraction = value, ""

        digits = whole + fraction
        if not digits:
            return "0.00"

        if len(fraction) == 0:
            if len(digits) == 1:
                return "0.0" + digits
            if len(digits) == 2:
                return "0." + digits
            return digits[:-2] + "." + digits[-2:]

        split = len(digits) - 2
        if split <= 0:
            return "0." + ("0" * (-split)) + digits
        return digits[:split] + "." + digits[split:]

    # ------------------------------------------------------------------
    # Discount
    # ------------------------------------------------------------------

    def _mine_discount(self, raw_value: Optional[str], terms: str) -> Optional[dict[str, Any]]:
        if not raw_value:
            # Trade terms can exist in payment terms without a rendered discount line.
            normalized_terms = self._mine_payment_terms(terms)
            if re.search(r"\b\d+\s*/\s*\d+\s+net\s+\d+\b", normalized_terms, re.I):
                rate = re.search(r"\b(\d+)\s*/\s*(\d+)\s+net\s+\d+\b", normalized_terms, re.I)
                return {
                    "type": "trade_terms",
                    "value": self._normalize_percent(rate.group(1)),
                    "applied_to": "subtotal",
                    "description": f"{normalized_terms} — conditional early-payment discount",
                    "conditional": True,
                }
            return None

        text = str(raw_value).strip()

        pct = self.DISCOUNT_PATTERNS["percentage"].search(text)
        if pct:
            rate = self._normalize_percent(pct.group("rate"))
            # A percentage discount rendered with its own line (and, usually,
            # a computed amount alongside it) has already been applied by the
            # vendor -- it is not an optional early-payment offer. Only the
            # unrendered "N/M net X" trade-terms case (handled above, when
            # raw_value is absent) represents a genuinely conditional
            # discount the recipient may or may not end up taking.
            return {
                "type": "percentage",
                "value": rate,
                "applied_to": "subtotal",
                "description": text.rstrip("."),
                "conditional": False,
            }

        if self.DISCOUNT_PATTERNS["rebate"].search(text):
            # A rebate "per agreement" is a fixed, already-negotiated
            # reduction rendered as an absolute amount -- not a percentage
            # and not conditional on future customer behaviour.
            return {
                "type": "amount",
                "value": self._extract_discount_amount(text),
                "applied_to": "subtotal",
                "description": text.rstrip("."),
                "conditional": False,
            }

        return {
            "type": "amount",
            "value": self._extract_discount_amount(text),
            "applied_to": "subtotal",
            "description": text.rstrip("."),
            "conditional": False,
        }

    def _mine_discount_amount(
        self,
        raw_value: Optional[str],
        number_format: str,
        discount: Optional[dict[str, Any]],
    ) -> str:
        if not raw_value:
            return "0.00"
        if discount and discount["conditional"]:
            return "0.00"
        return self._extract_discount_amount(str(raw_value))

    def _extract_discount_amount(self, text: str) -> str:
        candidates = re.findall(r"-?\s*(?:EUR\s*)?(\d[\d'.,]*)", text, re.I)
        if not candidates:
            raise InvoiceMiningError(f"Cannot mine discount amount: {text!r}")
        # Prefer the last monetary token, which is the rendered discount amount.
        return self._normalize_number(candidates[-1])

    # ------------------------------------------------------------------
    # Money / numbers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_quantity(value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if re.fullmatch(r"\d+\.0+", value):
            return value.split(".", 1)[0]
        return value.replace(",", ".")

    @staticmethod
    def _normalize_number(value: str) -> str:
        """
        Normalize a rendered numeric token while keeping it a string.

        Supported:
          12'345.67   -> 12345.67
          12.345,67   -> 12345.67
          12,345.67   -> 12345.67
          123,20      -> 123.20
          123.20      -> 123.20
        """
        value = value.strip()
        value = value.replace("EUR", "").replace("€", "")
        value = value.replace(" ", "").rstrip(".")

        sign = ""
        if value.startswith(("-", "+")):
            sign, value = value[0], value[1:]

        if "'" in value:
            value = value.replace("'", "")
        elif "." in value and "," in value:
            # Last separator determines the decimal separator.
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            parts = value.split(",")
            if len(parts[-1]) == 2:
                value = "".join(parts[:-1]) + "." + parts[-1]
            else:
                value = "".join(parts)
        elif "." in value:
            parts = value.split(".")
            if len(parts) > 2:
                # e.g. 1.234.567, but no comma: separators are grouping.
                value = "".join(parts[:-1]) + "." + parts[-1]

        if "." not in value:
            value += ".00"
        else:
            whole, fraction = value.split(".", 1)
            fraction = (fraction + "00")[:2]
            value = f"{whole}.{fraction}"

        return sign + value

    @staticmethod
    def _extract_money_string(value: str, number_format: str) -> str:
        matches = re.findall(r"-?[\d][\d'.,]*", str(value))
        if not matches:
            raise InvoiceMiningError(f"No money value found in {value!r}")
        return InvoiceMiner._normalize_number(matches[-1])

    def _detect_number_format(self, raw: dict[str, Any]) -> str:
        samples: list[str] = []
        for item in raw.get("items", []):
            if isinstance(item, dict):
                samples.extend([str(item.get("Unit Price", "")), str(item.get("Amount", ""))])
            elif isinstance(item, str):
                samples.append(item)
        samples.extend([str(raw.get("subtotal", "")), str(raw.get("total", ""))])

        text = " ".join(samples)
        if re.search(r"\d'\d", text):
            return "swiss"
        if re.search(r"\d+\.\d{3},\d{2}\b", text):
            return "eu_dot"
        if re.search(r"\d+,\d{2}\b", text) and not re.search(r"\d+,\d{3}\.\d{2}\b", text):
            return "eu_comma"
        return "us_comma"

    # ------------------------------------------------------------------
    # Bank / terms / currency
    # ------------------------------------------------------------------

    def _mine_bank(self, raw: Optional[str]) -> dict[str, str]:
        if not raw:
            return {"bank_name": "", "iban": "", "bic": "", "country": ""}

        text = str(raw)
        iban_match = re.search(r"IBAN:\s*([^|]+)", text, re.I)
        bic_match = re.search(r"BIC:\s*([^|]+)", text, re.I)
        bank_match = re.match(r"\s*Bank:\s*(.*?)(?:\s*\||$)", text, re.I)

        if not (iban_match and bic_match and bank_match):
            return {"bank_name": "", "iban": "", "bic": "", "country": ""}

        iban = re.sub(r"\s+", "", iban_match.group(1)).upper()
        return {
            "bank_name": bank_match.group(1).strip(),
            "iban": iban,
            "bic": bic_match.group(1).strip().upper(),
            "country": self.COUNTRY_FROM_IBAN.get(iban[:2], ""),
        }

    @staticmethod
    def _mine_bank_details(raw: Optional[str]) -> str:
        if not raw:
            return ""
        # Mirrors _mine_payment_terms: strip the field's own rendered
        # label rather than exposing it as part of the semantic value.
        return re.sub(r"^\s*Bank:\s*", "", str(raw).strip(), flags=re.I)

    @staticmethod
    def _mine_payment_terms(raw: Optional[str]) -> str:
        if not raw:
            return ""
        return re.sub(r"^Payment terms:\s*", "", str(raw).strip(), flags=re.I)

    @staticmethod
    def _mine_currency(raw: dict[str, Any]) -> str:
        text = f"{raw.get('subtotal', '')} {raw.get('total', '')}"
        if re.search(r"\bEUR\b|€", text, re.I):
            return "EUR"
        return ""

    # ------------------------------------------------------------------
    # Misc semantic metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _is_credit_note(header: list[str]) -> bool:
        return "CREDIT NOTE" in " ".join(header).upper()

    def _mine_edge_case(
        self,
        raw: dict[str, Any],
        vat: dict[str, Any],
        discount: Optional[dict[str, Any]],
    ) -> str:
        flags: list[str] = []
        if self._is_credit_note(raw.get("header", [])):
            flags.append("credit_note")
        if vat["variant"] == "mixed":
            flags.append("mixed_vat")
        if vat["variant"] == "reverse_charge":
            flags.append("reverse_charge")
        if vat["variant"] == "included":
            flags.append("vat_included")
        if discount and discount["conditional"]:
            flags.append("conditional_discount")
        if any(
            isinstance(item, dict)
            and re.search(
                r"Statutory VAT|Net prices|All prices include|reverse charge",
                str(item.get("Description", "")),
                re.I,
            )
            for item in raw.get("items", [])
        ):
            flags.append("field_bleed")
        return "+".join(flags) if flags else "none"

    @staticmethod
    def _clean_description(description: str) -> str:
        description = re.sub(
            r"\s+(?:"
            r"Statutory VAT(?:\s*\([^)]*\))?[^.]*applies\."
            r"|Net prices\. Statutory VAT applies\."
            r"|All prices include .*?VAT\."
            r"|VAT reverse charge mechanism.*"
            r"|Plus statutory VAT as detailed below\."
            r")",
            " ",
            description,
            flags=re.I,
        )
        description = re.sub(r"\s+«$", "", description)
        return re.sub(r"\s{2,}", " ", description).strip()

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result
