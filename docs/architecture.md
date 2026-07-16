# Architecture

```
 PDF file
    |
    v
 Ingestor            (src/.../ingesting/)      raw text/regions from the page
    |
    v
 Miner                (src/.../mining/)         semantic fields, still text
    |
    v
 Transformer           (src/.../transform.py)    typed values (Decimal, date, ...)
    |
    v
 Invoice model         (src/.../models/)         validated canonical record
    |
    v
 Serializers            (src/.../serialize.py)    JSON / CSV / text
    |
    v
 CLI                     (src/.../cli.py)         invoice-tool
```

`pipeline.py` is the only module that imports from every stage; it wires
them into the two functions that make up most of the project's public
API, `extract_invoice(path)` and `extract_invoice_batch(directory)`.
Nothing else needs to import `ingesting` or `mining` directly.

## Component responsibilities

**Ingesting** (`ingesting/`) opens a PDF page with `pdfplumber` and pulls
out the raw regions an invoice is expected to contain -- the header block,
the "bill to" address, the line-item table or paragraph, totals, discount
line, bank details -- as plain strings/dicts. It knows *where* things are
on the page, not what they mean. `TableLayoutIngester` and
`ParagraphLayoutIngester` share a common base (`InvoiceIngester` /
`PdfIngester`) and differ only in how they read line items, chosen per
document by whether `pdfplumber` finds an explicit table
(`pipeline.ingest_invoice_pdf`).

**Mining** (`mining/`) takes that raw dict and identifies *semantic*
fields from it: which line is the invoice number, which number format the
document uses, whether a discount is conditional on early payment, and so
on. Its output values are still strings (see `docs/pipeline.md`), but they
are the strings that matter, not the raw page layout. It also computes
provenance/diagnostic tags -- `vat_variant`, `discount_variant`,
`number_format`, `layout`, `edge_case` -- that describe *how* a document
expressed something, kept on the final `Invoice` for anyone who wants to
audit an extraction (`docs/data-model.md`).

**Transform** (`transform.py`) turns those strings into canonical Python
types and derives values the miner deliberately leaves for this layer:
Decimal/date coercion, filling in an unstated VAT rate from a stated VAT
amount (or vice versa), and computing a discount's actual monetary effect
from its type and conditionality. It raises `TransformationError` when a
value can't be coerced -- it does not decide whether the result is a
*valid* invoice.

**Models** (`models/`) is the validation layer and the project's one
public data contract: `Invoice`, with `Address`, `LineItem`, and
`Discount` as its structured sub-fields. Field constraints (non-negative
amounts, 0-100% rate bounds, non-empty identifiers) and cross-field rules
(`due_date >= invoice_date`, total sign vs. credit-note status) are
enforced by Pydantic at construction time. `subtotal`, `total`,
`consistency`, and `consistency_note` are computed fields derived from the
other data, not constructor inputs -- see `docs/data-model.md` for why.

**Serialize** (`serialize.py`) converts a validated `Invoice` (or a list
of them) into JSON, CSV, or a human-readable text summary. It has no
knowledge of PDFs, mining, or validation rules -- only of the `Invoice`
model.

**CLI** (`cli.py`) is a thin `argparse` wrapper over `pipeline.py` and
`serialize.py`: two subcommands (`extract`, `batch`), three output
formats, and consistent stage-labeled error reporting (`docs/cli.md`).

## Why this split

Keeping ingestion/mining (text in, text out) separate from
transformation/validation (text in, typed and checked data out) means a
malformed value's failure mode tells you which layer is responsible: a
raw region the ingester couldn't find is an `IngestionError`; a value the
miner couldn't semantically identify is a `MiningError` (raised by the
existing `InvoiceMiningError`, which is now a subclass); a value that
doesn't coerce to its canonical type is a `TransformationError`; a value
that coerces fine but breaks a structural or business rule is a
`pydantic.ValidationError`. See `docs/pipeline.md` for the full failure
mode reference.
