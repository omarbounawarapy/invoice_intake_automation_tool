from .invoice_ingester import InvoiceIngester
from pdfplumber import open as pdfopen
from collections import defaultdict
import sys 

COLUMNS = {
        "Description": (40, 300),
        "Qty": (300, 365),
        "Unit Price": (365, 480),
        "Amount": (480, 550),
    }

class TableLayoutIngester(InvoiceIngester): 

    @staticmethod
    def start_word(words) : 
        return next(
            w for w in words
            if w["text"].lower() == "description"
        )

    @staticmethod
    def end_word(words) : 
        return next(
                    w for w in words
                    if w["text"].lower().startswith("subtotal")
                )
        
    def extract_items_region(self, page):
        return self.extract_between_anchors(
            page,
            "Description",
            "subtotal",
        )


    def extract_items(self,page):
        words = page.extract_words()
        start_word = self.start_word(words)
        end_word = self.end_word(words)

        table_top = start_word["top"]
        table_bottom = end_word["top"]

        # --------------------------------------------------
        # 2. Keep only words inside the table
        # --------------------------------------------------

        words = [
            w for w in words
            if table_top < w["top"] < table_bottom
        ]

        # --------------------------------------------------
        # 3. Group words by physical line
        # --------------------------------------------------

        lines = defaultdict(list)

        for word in words:
            lines[round(word["top"], 2)].append(word)

        # --------------------------------------------------
        # 4. Build a row for every physical line
        # --------------------------------------------------

        rows = []

        for _, line_words in sorted(lines.items()):
            row = {
                "Description": [],
                "Qty": [],
                "Unit Price": [],
                "Amount": [],
            }

            for word in sorted(line_words, key=lambda w: w["x0"]):
                x = word["x0"]
                text = word["text"]

                for column, (left, right) in COLUMNS.items():
                    if left <= x < right:
                        row[column].append(text)
                        break

            row = {
                column: " ".join(values)
                for column, values in row.items()
            }

            # Ignore the header
            if row["Description"].lower() == "description":
                continue

            rows.append(row)

        # --------------------------------------------------
        # 5. Convert physical lines → logical invoice items
        # --------------------------------------------------

        items = []

        for row in rows:

            if self.is_new_item(row):
                items.append(row)

            else:
                if items:
                    items[-1] = self.expand_item(items[-1], row)

        return items

    @staticmethod
    def is_new_item(item: dict) -> bool:
        return all(
            item[field] != ""
            for field in ("Description", "Qty", "Unit Price", "Amount")
        )

    @staticmethod
    def expand_item(item: dict, continuation: dict) -> dict:
        return {
            **item,
            "Description": (
                item["Description"]
                + " "
                + continuation["Description"]
            ).strip(),
        }



