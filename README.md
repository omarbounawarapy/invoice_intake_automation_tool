# Invoice Intake Automation Tool

Extracts, normalizes, and validates structured data from semi-structured
invoice PDFs, and exports it to **JSON, CSV, or Excel (XLSX)** through a
single command-line tool.

## The problem

Invoices arrive as PDFs in inconsistent layouts -- some as neat tables,
some as prose paragraphs, in different number formats (`1,234.56`,
`1'234.56`, `1.234,56`), with discounts and VAT phrased a dozen different
ways. Turning a folder of them into a spreadsheet you can actually work
with is slow, repetitive, and error-prone by hand. This tool automates
that: point it at a PDF (or a folder of them) and get back a typed,
validated record with a predictable schema, ready for JSON, CSV, or
Excel.

## 30-second demo

```bash
invoice-tool extract examples/invoices/INV-2026-0001.pdf
```

```
Invoice INV-2026-0001                                                  CORRECT
Praxis Consulting Group AG (AT)  ->  Bergkristall Maschinenbau GmbH (DE)
Date: 2026-04-15    Due: 2026-05-15    Currency: EUR
------------------------------------------------------------------------------
Line items
  Travel expenses (Frankfurt–Zürich)                 3 x 26,614.40 = 79,843.20
  Software licence renewal — 50 seats                  1 x 9,583.60 = 9,583.60
  Executive workshop (2 days)                          1 x 2,614.80 = 2,614.80
  Hardware procurement — 4 workstations               3 x 9,834.20 = 29,502.60
  Compliance audit preparation (regul...                50 x 185.70 = 9,285.00
  Legal opinion — cross-border financing             1 x 46,646.20 = 46,646.20
  Consulting hours — Senior Partner                  1 x 32,740.50 = 32,740.50
------------------------------------------------------------------------------
Subtotal:                                                       210,215.90 EUR
Discount (2%):                                                   -4,204.32 EUR
VAT (20%):                                                       42,043.18 EUR
==============================================================================
Total:                                                          248,054.76 EUR
```

Same invoice, machine-readable (`line_items` truncated to one entry below
for length -- the real output has all seven):

```bash
invoice-tool extract examples/invoices/INV-2026-0001.pdf --format json
```

```json
{
  "invoice_id": "INV-2026-0001",
  "vendor": "Praxis Consulting Group AG",
  "vendor_country": "AT",
  "recipient": "Bergkristall Maschinenbau GmbH",
  "recipient_country": "DE",
  "invoice_date": "2026-04-15",
  "due_date": "2026-05-15",
  "currency": "EUR",
  "line_items": [
    {
      "description": "Travel expenses (Frankfurt–Zürich)",
      "quantity": "3",
      "unit_price": "26614.40",
      "amount": "79843.20",
      "vat_rate": "0.20"
    }
  ],
  "subtotal": "210215.90",
  "discount_amount": "4204.32",
  "vat_amount": "42043.18",
  "total": "248054.76",
  "consistency": "correct"
}
```

And when a document's printed total doesn't actually match its own line
items -- which happens on real invoices -- the tool says so instead of
quietly reporting the wrong number:

```bash
invoice-tool extract examples/invoices/INV-2026-0002.pdf
```

```
Invoice INV-2026-0002                                              TOTAL ERROR
...
Total:                                                          183,313.83 EUR

! Displayed total 188813.24 differs from computed total 183313.83 by +5499.41 (+3.00%).
```

Every example above is real, reproducible output from this repository --
not illustrative text. Run `pytest` and see `examples/README.md` and
`examples/outputs/`.

## Features

* **PDF ingestion** -- table and paragraph invoice layouts, three number
  formats (US/UK, Swiss, German)
* **Structured field mining** -- invoice/date fields, parties, VAT,
  discounts (percentage, flat amount, and conditional trade terms)
* **Normalization** -- typed, `Decimal`-precise canonical records, not
  floats or raw strings
* **Validation** -- a typed Pydantic schema with structural and
  cross-field business rules (see [Design decisions](#design-decisions))
* **Reconciliation** -- computed totals are checked against what the
  document actually prints, and disagreements are surfaced, not hidden
* **JSON, CSV, and Excel (XLSX) output**, plus a readable terminal summary
* **A real CLI** -- `invoice-tool extract` / `invoice-tool batch`, with
  proper exit codes for scripting
* **Automated tests** -- 200+ tests, including regression tests against
  externally-sourced ground truth for every example invoice

## Capability matrix

| Capability | Status |
| --- | --- |
| Digital (text-layer) PDFs | Supported |
| Table-layout invoices | Supported |
| Paragraph-layout invoices | Supported |
| US/UK, Swiss, and German number formats | Supported |
| Percentage, flat-amount, and conditional (trade-terms) discounts | Supported |
| VAT rate/amount derivation when only one is stated | Supported |
| Total/subtotal reconciliation against the printed document | Supported |
| JSON export | Supported |
| CSV export | Supported |
| Excel (XLSX) export, with a summary + line-items workbook | Supported |
| Batch processing of a directory | Supported |
| Scanned PDFs / OCR | Not supported |
| Handwritten documents | Not supported |
| Multi-page invoices | Not supported (first page only) |
| Currencies other than EUR | Not reliably detected (see [Limitations](docs/limitations.md)) |
| Full accounting/tax compliance | Not supported -- this is a normalization tool, not compliance software |

## Architecture

```
PDF
 |
 v
Ingestor            raw text/regions from the page
 |
 v
Miner                semantic fields (still text)
 |
 v
Transformer           typed values (Decimal, date), derives implicit VAT/discount figures
 |
 v
Invoice model          validated canonical record (Pydantic)
 |
 v
Serializer               JSON / CSV / XLSX / terminal text
 |
 v
CLI                       invoice-tool
```

Each stage has one job and one failure mode (`IngestionError`,
`MiningError`, `TransformationError`, `pydantic.ValidationError`) so a
malformed document tells you which layer is responsible rather than
producing a bare traceback. Full write-up in
[`docs/architecture.md`](docs/architecture.md).

## Installation

Requires Python 3.12+.

```bash
git clone <this-repository>
cd invoice-intake-automation-tool
pip install -e .
```

```bash
invoice-tool --help
```

For development (running the test suite):

```bash
pip install -e ".[dev]"
pytest
```

## Usage

```bash
# Human-readable summary (default)
invoice-tool extract invoice.pdf

# Machine-readable formats
invoice-tool extract invoice.pdf --format json
invoice-tool extract invoice.pdf --format csv --output result.csv
invoice-tool extract invoice.pdf --format xlsx --output result.xlsx

# Exit non-zero if the invoice's totals don't reconcile (useful in CI/scripts)
invoice-tool extract invoice.pdf --strict

# Process every PDF in a folder
invoice-tool batch ./invoices/
invoice-tool batch ./invoices/ --format xlsx --output all_invoices.xlsx
```

Full command reference, flags, and exit codes:
[`docs/cli.md`](docs/cli.md).

### As a library

```python
from invoice_intake_automation_tool import extract_invoice

invoice = extract_invoice("invoice.pdf")
print(invoice.total, invoice.consistency)
```

## Design decisions

* **Extraction and semantic mining are separate stages** (`ingesting/` vs
  `mining/`) so that "where is this text on the page" and "what does this
  text mean" can be worked on, tested, and reasoned about independently.
* **Normalization is a distinct stage from mining.** The mining layer
  produces semantically-identified but still-textual values by design (its
  own docstring states this contract); `transform.py` is solely
  responsible for turning those into typed, computed values.
* **The canonical `Invoice` model is the one public data contract.**
  Everything upstream exists to produce one; everything downstream
  (serializers, CLI) consumes one. Internal classes (ingesters, the
  miner) are not part of the public API.
* **`Decimal`, never `float`, for every monetary value** -- financial
  arithmetic done in binary floating point silently loses cents.
* **`subtotal` and `total` are computed fields, not stored input.** They
  are defined as functions of `line_items` (and `discount_amount`/
  `vat_amount`), so it is structurally impossible to construct an
  `Invoice` whose total disagrees with its own line items. See
  [`docs/data-model.md`](docs/data-model.md).
* **Validation is separate from -- and stricter than -- reconciliation.**
  A missing required field, a negative amount, or `due_date` before
  `invoice_date` rejects the document (`pydantic.ValidationError`). A
  printed total that doesn't match the computed one does *not* reject the
  document -- it's a genuine, useful fact about a real invoice, reported
  via `consistency`/`consistency_note` rather than hidden behind a
  crash.
* **A plain CLI over `argparse`, not a larger framework.** Two
  subcommands and three flags don't need one; every dependency in this
  project (`pdfplumber`, `pydantic`, `openpyxl`) earns its place doing
  something the standard library can't.

## Testing

```bash
pytest
```

200+ tests across three layers:

* **Unit** (`tests/unit/`) -- every transformation function and
  validation rule tested directly against representative format
  variations and edge cases.
* **Integration** (`tests/integration/`) -- the full pipeline wired
  together, the CLI's commands and exit codes, and batch processing
  (including a file that fails partway through a batch).
* **Regression** (`tests/integration/test_regression.py`) -- every field
  of every example invoice checked against externally-sourced ground
  truth (`examples/ground_truth/`), not this codebase's own idea of the
  right answer.

## Example data

Five real (synthetic) invoices with externally-sourced reference values
live in [`examples/`](examples/README.md), along with the real output
this tool produces for each of them. See that file for provenance and a
licensing note.

## Limitations

This is a normalization tool for structured, text-based PDFs -- not OCR,
not accounting/compliance software, not a guarantee of perfect
extraction. Full, honest accounting of what it does and doesn't handle:
[`docs/limitations.md`](docs/limitations.md).

## Freelance use case

If you have a folder of vendor invoice PDFs and need them as structured
data -- for a spreadsheet, an accounts-payable import, or feeding another
system -- this tool turns that into one command:

```bash
invoice-tool batch ./client_invoices/ --format xlsx --output invoices.xlsx
```

It won't handle scanned documents or replace an accountant's judgment
call on an ambiguous line item, but for consistent, text-based PDF
invoices it removes the manual transcription step and flags documents
worth a second look via `consistency`.

## Project snapshot

* Python 3.12+
* Typed, validated canonical invoice model (Pydantic)
* JSON, CSV, and Excel (XLSX) output, plus a readable terminal summary
* `invoice-tool` CLI with `extract` and `batch` commands
* 200+ automated tests, including regression tests against externally
  sourced ground truth
* Three dependencies: `pdfplumber`, `pydantic`, `openpyxl`

## Documentation

* [`docs/architecture.md`](docs/architecture.md) -- component boundaries and data flow
* [`docs/data-model.md`](docs/data-model.md) -- the canonical schema, field by field
* [`docs/pipeline.md`](docs/pipeline.md) -- ingest → mine → transform → validate → serialize, and where each failure type comes from
* [`docs/cli.md`](docs/cli.md) -- full command reference
* [`docs/limitations.md`](docs/limitations.md) -- honest scope boundaries

## Future improvements

Realistic, not aspirational:

* Structured IBAN/BIC fields (the mining layer already parses these
  internally; only the public output would need to change -- see
  `docs/data-model.md`)
* Currency detection beyond EUR
* Multi-page invoice support
* An OCR pre-processing step for scanned documents (a genuinely separate
  concern from this project's current text-layer-only scope)

## License

Apache License 2.0 -- see [`LICENSE`](LICENSE). Example invoice data is
synthetic; see [`examples/README.md`](examples/README.md) for its
provenance and a licensing caveat.
