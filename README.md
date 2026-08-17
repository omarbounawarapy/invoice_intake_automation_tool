# Invoice Intake Automation Tool

Python tool for turning heterogeneous invoice PDFs, CSV files, and Excel spreadsheets into a clean, validated dataset suitable for accounting or operational review.

The project simulates a small-business automation job: invoice information arrives in different layouts and formats, staff currently clean it manually, and the client wants one repeatable command that produces a consistent spreadsheet plus a clear validation report.

> **Scope:** this is a focused batch-processing utility, not a general document-processing framework.

## Problem

Small businesses often receive invoices from multiple suppliers with inconsistent layouts, column names, number formats, and date formats. Manual consolidation is repetitive and makes validation errors easy to miss.

This tool provides a repeatable workflow:

```text
PDF / CSV / XLSX
       |
       v
   Extraction
       |
       v
  Normalization
       |
       v
 Schema validation
       |
       v
 Duplicate handling
       |
       v
     Export
   /    |     \
  v     v      v
CSV    XLSX   Report
```

## Business Use Case

A small construction or professional-services business receives supplier invoices every week. The administrative team needs a normalized table containing invoice and line-item information so it can be reviewed, filtered, reconciled, or imported into another workflow.

The intended client request is deliberately small:

> "Give me the invoice files we receive every week and produce one clean spreadsheet with the fields we care about. Tell me which records need attention instead of silently dropping them."

## Supported Inputs

The first version supports:

- Digital/text PDF invoices
- CSV supplier exports
- XLSX supplier exports

It intentionally does **not** support scanned documents or images.

### Why there is no OCR

The demonstration sources are digital documents with machine-readable content. Adding OCR would introduce a second extraction problem without improving the core portfolio signal. OCR can be added as a separate project when a real client requirement justifies it.

## Canonical Output Schema

The normalized dataset uses one row per invoice line.

| Field | Description |
|---|---|
| `source_file` | Original input filename |
| `invoice_number` | Supplier invoice identifier |
| `invoice_date` | Normalized invoice date (`YYYY-MM-DD`) |
| `due_date` | Normalized due date when available |
| `supplier_name` | Supplier/vendor name |
| `customer_name` | Customer/bill-to name |
| `purchase_order` | Purchase-order reference when available |
| `currency` | Currency code when available |
| `line_number` | Invoice line number |
| `description` | Original line-item description after whitespace cleanup |
| `quantity` | Normalized numeric quantity |
| `unit_price` | Normalized monetary value |
| `line_total` | Normalized line amount |
| `tax_amount` | Invoice tax amount when available |
| `shipping_amount` | Shipping amount when available |
| `subtotal` | Invoice subtotal when available |
| `total_due` | Final invoice amount when available |
| `validation_status` | `VALID` or `INVALID` |

Values that are absent in the source remain missing. The tool does not invent business data such as `0`, `UNKNOWN`, or `N/A` merely to fill a blank field.

## Normalization Rules

### Dates

Dates are converted to `YYYY-MM-DD` where the source provides an unambiguous value.

Ambiguous or malformed dates are reported as validation errors rather than guessed.

### Monetary values

Common representations such as the following are normalized to a numeric monetary value:

```text
$1,250.00
1,250.00
1 250.00
1250.00
```

### Text

The normalizer removes surrounding whitespace, repeated whitespace, and line-break artifacts while preserving the meaning of the original description.

### Column aliases

Supplier spreadsheet headers such as `Qty`, `QTY`, and `quantity` are mapped to the canonical `quantity` field. The same approach is used for common date and amount aliases.

## Validation Behavior

Validation occurs after extraction and normalization.

The tool checks, where applicable:

- invoice number is present
- invoice date is valid
- line description is present
- quantity is greater than zero
- unit price is non-negative
- line total is non-negative
- `quantity × unit_price` agrees with `line_total` within a small currency tolerance
- invoice totals are internally consistent when the source provides enough information

A malformed file or record does not terminate the whole batch. It is reported and processing continues for the remaining inputs.

## Duplicate Handling

Duplicate line records are identified using the normalized invoice identity:

```text
(invoice_number, line_number, supplier_name)
```

Exact duplicates are kept once and reported in the processing summary. The tool does not silently aggregate duplicate business records.

## Outputs

A successful run produces the following artifacts:

```text
data/output/
├── cleaned.csv
├── cleaned.xlsx
├── validation_report.json
└── processing.log
```

### `cleaned.csv`

The canonical one-row-per-invoice-line dataset. This is the simplest machine-readable output for downstream systems.

### `cleaned.xlsx`

A review-friendly workbook containing:

- `invoice_lines` — normalized line-item records
- `invoice_summary` — one row per invoice
- `validation_issues` — records requiring attention

### `validation_report.json`

A machine-readable processing summary containing file counts, record counts, duplicate counts, and validation issues.

Example:

```json
{
  "files_processed": 6,
  "files_succeeded": 5,
  "files_failed": 1,
  "records_extracted": 42,
  "valid_records": 39,
  "invalid_records": 3,
  "duplicates_removed": 2
}
```

### `processing.log`

Operational log showing files processed, extraction results, validation failures, and unexpected errors.

## Installation

Requires Python 3.12 or newer.

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the project:

```bash
pip install -e .
```

Install development dependencies when running the test suite:

```bash
pip install -e ".[dev]"
```

## Usage

Place input files in `data/input/` and run:

```bash
python -m src.cli \
    --input ./data/input \
    --output ./data/output
```

For a stricter CI-style run that returns a non-zero exit code when validation errors are present:

```bash
python -m src.cli \
    --input ./data/input \
    --output ./data/output \
    --strict
```

## Example Run

```text
$ python -m src.cli --input ./data/input --output ./data/output

Processing 6 files...

invoice_smartsheet.pdf   8 lines   VALID
invoice_gmu.pdf          5 lines   VALID
invoice_georgia.pdf      3 lines   VALID
supplier_export.xlsx    18 lines   VALID
supplier_export.csv     12 lines   2 warnings
malformed_invoice.pdf     0 lines   EXTRACTION_ERROR

42 records extracted
39 valid
3 invalid
2 duplicates removed

Output written to ./data/output/
```

The values above illustrate the shape of the console output; they are not benchmark or dataset claims.

## Architecture

The application deliberately uses ordinary Python modules rather than a framework.

```text
src/
└── invoice_normalizer/
    ├── cli.py
    ├── models.py
    ├── extract.py
    ├── normalize.py
    ├── validate.py
    ├── export.py
    └── report.py
```

### `models.py`

Defines the canonical invoice, invoice-line, validation-issue, and processing-result models.

### `extract.py`

Reads supported files and converts them into raw invoice records. PDF parsing is handled with `pdfplumber`; CSV/XLSX ingestion is handled with `pandas`.

### `normalize.py`

Maps source-specific values into the canonical schema and normalizes dates, amounts, whitespace, and common column aliases.

### `validate.py`

Applies business validation rules and returns explicit validation issues.

### `export.py`

Writes the normalized CSV and review-oriented Excel workbook.

### `report.py`

Produces the JSON processing summary and validation issue report.

### `cli.py`

Parses command-line arguments and orchestrates one batch run.

There are intentionally no plugin registries, event buses, dependency-injection containers, abstract factories, or generic pipeline abstractions. The application is small enough that direct composition is clearer.

## Technology Choices

| Technology | Purpose |
|---|---|
| Python 3.12+ | Runtime and application code |
| pandas | CSV/XLSX ingestion and tabular normalization |
| pdfplumber | Text/table extraction from digital PDFs |
| Pydantic | Explicit validation of the canonical data contract |
| openpyxl | XLSX workbook generation through pandas |
| pytest | Automated tests |
| `logging` | Operational logging without another dependency |

## Testing

Tests are designed around real failure modes rather than arbitrary coverage percentages.

The suite covers:

- normal PDF extraction
- multi-page PDF extraction
- CSV input
- XLSX input
- missing fields
- malformed dates
- malformed monetary values
- invalid quantities
- line-total mismatches
- duplicate records
- extraction failures
- exact output columns
- expected Excel workbook sheets
- end-to-end extraction → normalization → validation → export

Run the test suite with:

```bash
pytest
```

The tests should use small local fixtures and must not require network access.

## Project Data

The demonstration deliberately separates **real public source material** from **synthetic messy test cases**.

## Project Data and Source Attribution

The project uses the publicly available **InvoiceBenchmark** synthetic invoice dataset:

https://huggingface.co/datasets/jngb-labs/InvoiceBenchmark

The dataset provides synthetic invoice documents together with structured ground-truth records. The invoices contain fictional business and transaction information and are used solely to provide a reproducible corpus for extraction and validation testing.

For this project, the PDF invoice files are treated as input data, while the accompanying ground-truth records are used as expected outputs for automated validation.

The repository does not claim that the dataset represents real confidential business records. It is used as a controlled demonstration of a document-ingestion workflow that could be adapted to a client's actual invoice formats.

Dataset contents are obtained from the original dataset source rather than being represented as proprietary or original project data. Users should consult the dataset repository for its current license, attribution requirements, and permitted uses.

The repository may also contain small synthetic CSV/XLSX fixtures created specifically to test malformed values, missing fields, duplicate records, and normalization rules.


### Synthetic test cases

`data/synthetic/` contains deliberately modified examples derived from the public source material. These cases introduce controlled inconsistencies such as:

- alternate column names
- multiple date formats
- currency symbols
- whitespace variations
- missing values
- malformed numbers
- duplicate rows
- arithmetic mismatches

Synthetic cases exist to exercise validation and error handling. They are not presented as real customer data.

To retrieve the documented public source material when the downloader is implemented:

```bash
python scripts/download_sources.py --output ./data/input
```

## Limitations

This is intentionally a small batch-processing application.

It does not currently provide:

- OCR for scanned documents
- image/PDF handwriting recognition
- LLM-based extraction
- accounting-system API integration
- database persistence
- web UI
- background job scheduling
- cloud deployment
- arbitrary invoice-template discovery

The PDF extraction logic is designed for the documented demonstration layouts, not for every invoice format in existence. A real client engagement would expand the supported layouts only as concrete requirements justify it.

## What This Project Demonstrates

This project is designed to demonstrate practical freelance engineering rather than maximum technical complexity.

It shows that the engineer can:

- take heterogeneous real-world business documents
- extract structured information from them
- normalize inconsistent representations
- define and enforce a stable output schema
- validate business rules
- handle malformed records without losing the whole batch
- produce both machine-readable and human-reviewable outputs
- provide useful operational logging
- write tests around failure modes
- document a repeatable client-facing workflow

The intended portfolio signal is simple:

> **Give me messy business input and a desired output schema, and I can turn it into a reliable, repeatable data-processing tool.**

## License

This project's source code is released under the Apache License 2.0. Source documents referenced in the dataset section remain subject to their respective publishers' terms and are not relicensed by this repository.