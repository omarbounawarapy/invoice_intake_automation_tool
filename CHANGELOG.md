# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-19

Initial release.

### Added

- PDF ingestion for table-layout and paragraph-layout invoices.
- Number-format parsing for US/UK, Swiss, and German conventions.
- Semantic field mining: invoice/date fields, parties, VAT, and discounts
  (percentage, flat amount, and conditional trade terms).
- Typed, `Decimal`-precise canonical `Invoice` model (Pydantic), with
  structural and cross-field validation.
- Total/subtotal reconciliation against the document's own printed
  values, surfaced via a `consistency` field rather than hidden.
- `invoice-tool` CLI with `extract` and `batch` commands, JSON/CSV/XLSX
  export, and a readable terminal summary.
- `--strict` flag for non-zero exit on reconciliation mismatches.
- Public library API (`extract_invoice`, `extract_invoice_batch`).
- Unit, integration, and regression test suite (200+ tests), including
  regression tests against externally-sourced ground truth for every
  example invoice.
- Curated example dataset (`examples/`) with source PDFs, ground truth,
  and real tool output for five invoices.
- Documentation: architecture, data model, pipeline, CLI reference, and
  limitations.

[0.1.0]: https://github.com/omarbounawarapy/invoice_intake_automation_tool/releases/tag/v0.1.0
