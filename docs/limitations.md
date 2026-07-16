# Limitations

This tool is a document-normalization utility, not accounting or
compliance software. It is honest about what it does not handle so that
using it does not require discovering these boundaries the hard way.

## Input documents

* **Single-page, digitally generated PDFs only.** The ingestion layer
  reads `pdfplumber`'s text/table extraction from `pdf.pages[0]`; a
  multi-page invoice's later pages are never read.
* **No OCR.** A scanned or photographed invoice (an image with no
  embedded text layer) will fail at the ingestion stage, not silently
  produce empty fields.
* **No handwritten documents.** Same reason.
* **Layout is a binary heuristic.** `ingest_invoice_pdf` chooses between a
  table-reading path and a paragraph-reading path based only on whether
  `pdfplumber` finds an explicit table on the page. The project's own
  reference dataset distinguishes a third `mixed` layout category (a
  table for line items alongside prose for totals, for example) that this
  heuristic cannot represent -- it will pick whichever of the two paths
  happens to extract usable data, not a hybrid of both.
* **Anchor-based extraction is brittle to unfamiliar phrasing.** The
  ingester locates fields by looking for specific anchor phrases ("Bill
  to", "Due:", VAT/discount patterns in mining). An invoice using
  substantially different wording than the reference dataset's templates
  is more likely to fail extraction than to silently mis-extract.

## Currency and internationalization

* **Currency detection only recognizes EUR.** All five example invoices
  are EUR-denominated; the mining layer's currency detection has not been
  exercised against other currencies. An invoice in another currency will
  most likely come through with `currency: null` rather than a wrong
  guess -- see `docs/data-model.md` on why unrecognized values become
  `null`, not a default.
* **Country/address parsing assumes European conventions** (a
  `postal_code city, country` line format). Non-European address formats
  are not represented in the reference dataset this project was built and
  tested against.

## Financial reconciliation

* **The reconciliation check (`consistency`) covers subtotal and total
  only.** Per-line arithmetic (`quantity * unit_price == amount`) is
  assumed correct from the source and not independently re-verified --
  see `docs/data-model.md` for the accounting assumption the total
  formula itself relies on. This project's reference data does not
  include an example with a per-line arithmetic error, so no check was
  built for one rather than building an unverified one.
* **VAT rate/amount derivation assumes a single applicable rate.** When a
  document genuinely has mixed VAT rates across line items, the top-level
  `vat_rate` is correctly left `null` (see `vat_variant: "mixed"`), but no
  attempt is made to derive or reconcile per-line rates beyond what the
  document states explicitly.
* **`discount.applied_to` is always treated as the subtotal.** Every
  discount in the reference dataset applies to the subtotal; a discount
  applied to a different base is not specially handled.
* **Credit-note sign conventions are unverified.** `is_credit_note` is
  mined from the document header and currently only affects whether a
  negative `total` is accepted (see `docs/data-model.md`). No credit-note
  example was available in this project's reference data, so no
  assumption is made about whether individual line amounts should be
  negative on a credit note -- they remain constrained to be
  non-negative, same as an ordinary invoice.

## Banking details

* **`bank_details` is one unparsed string**, not structured IBAN/BIC
  fields, even though the mining layer's internal logic already parses
  IBAN/BIC to infer `vendor_country`. See "Why not structured IBAN/BIC
  fields?" in `docs/data-model.md`.

## Diagnostic tag vocabulary

* **`layout`, `number_format`, `vat_variant`, `discount_variant`, and
  `edge_case`** are whatever string the mining layer produces, not
  validated against a closed list. This project's fixture set (5-6
  invoices) demonstrates only a handful of the values these can take; the
  mining layer was evidently built against a larger reference benchmark
  (up to 200 invoices, per the range in the project's original
  exploration script) that this repository does not include in full --
  see `examples/README.md`.

## Scale

* **Not designed for high-volume/concurrent processing.** `batch`
  processes files sequentially in one process; there is no queueing,
  retries, or parallelism. For a handful to a few hundred invoices at a
  time (the scale this tool targets), that is sufficient; it is not
  intended for a high-throughput production pipeline.

## What this project is not

Explicitly, and by design: not OCR software, not accounting or
tax-compliance software, not an ERP system, not a guarantee of perfect
extraction. It automates the mechanical, repetitive part of invoice data
entry for structured, text-based PDFs, and is explicit -- via
`consistency`, `null` fields, and pipeline-stage-labeled errors -- about
where it is and isn't confident in what it found.
