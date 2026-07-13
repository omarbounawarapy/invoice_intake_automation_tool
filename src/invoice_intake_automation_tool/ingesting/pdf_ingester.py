from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


from pdfplumber import open as pdfopen
from collections import defaultdict

from ..errors import IngestionError


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


class PdfIngester:
    """
    Low-level PDF document extraction primitives.

    This class knows about:
    - words
    - physical lines
    - anchors
    - regions

    It does NOT know about invoices, addresses, totals, etc.
    """

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def extract_lines_after_anchor(
        self,
        page,
        anchor: str,
        num_lines: int,
        *,
        include_anchor: bool = False,
    ) -> list[str]:
        lines = self.get_lines(page)
        index = self.find_line_index(lines, anchor)

        start = index if include_anchor else index + 1
        end = start + num_lines

        return self.lines_to_text(lines[start:end])

    def extract_lines_before_anchor(
        self,
        page,
        anchor: str,
        num_lines: int,
        *,
        include_anchor: bool = False,
    ) -> list[str]:
        lines = self.get_lines(page)
        index = self.find_line_index(lines, anchor)

        end = index + 1 if include_anchor else index
        start = max(0, end - num_lines)

        return self.lines_to_text(lines[start:end])

    def extract_between_anchors(
        self,
        page,
        start_anchor: str,
        end_anchor: str,
        *,
        include_start: bool = False,
        include_end: bool = False,
    ) -> list[str]:
        lines = self.get_lines(page)

        start_index = self.find_line_index(lines, start_anchor)
        end_index = self.find_line_index(
            lines,
            end_anchor,
            start_index=start_index + 1,
        )

        start = start_index if include_start else start_index + 1
        end = end_index + 1 if include_end else end_index

        return self.lines_to_text(lines[start:end])

    
    def extract_line_containing_anchor(self,page, anchor: str) -> str:
        lines = self.get_lines(page)


        for line in lines:
            text = " ".join(word.text for word in line)

            if anchor in text:
                return text

        raise IngestionError(f"Anchor {anchor!r} not found.")

    def extract_lines_containing_anchor(self,page, anchor: str) -> str:
            lines = self.get_lines(page)
            results = []

            for line in lines:
                text = " ".join(word.text for word in line)
    
                if anchor in text:
                    results.append(text)
            if not results : raise IngestionError(f"Anchor {anchor!r} not found.")
            
            return results
    

    def extract_section_after_anchor(
        self,
        page,
        anchor: str,
        num_lines: int,
        *,
        skip: int = 0,
    ) -> list[str]:
        """
        Convenience method for the common:
            find anchor
            take N lines after it
            skip first K lines
        """
        lines = self.extract_lines_after_anchor(
            page,
            anchor,
            num_lines + skip,
        )

        return lines[skip:]

    # ------------------------------------------------------------------
    # Line handling
    # ------------------------------------------------------------------

    def get_lines(self, page) -> list[list[Word]]:
        """
        Extract words and group them into physical PDF lines.
        """
        words = [
            Word(
                text=w["text"],
                x0=w["x0"],
                x1=w["x1"],
                top=w["top"],
                bottom=w["bottom"],
            )
            for w in page.extract_words()
        ]

        grouped: dict[float, list[Word]] = {}

        for word in words:
            y = round(word.top, 2)
            grouped.setdefault(y, []).append(word)

        return [
            sorted(line, key=lambda w: w.x0)
            for _, line in sorted(grouped.items())
        ]

    @staticmethod
    def lines_to_text(lines: Iterable[list[Word]]) -> list[str]:
        return [
            " ".join(word.text for word in line)
            for line in lines
        ]

    # ------------------------------------------------------------------
    # Anchor handling
    # ------------------------------------------------------------------

    @staticmethod
    def find_line_index(
        lines: list[list[Word]],
        anchor: str,
        *,
        start_index: int = 0,
    ) -> int:
        anchor = anchor.lower()

        for index in range(start_index, len(lines)):
            line_text = " ".join(
                word.text for word in lines[index]
            ).lower()

            if anchor in line_text:
                return index

        raise IngestionError(
            f"Anchor {anchor!r} not found."
        )