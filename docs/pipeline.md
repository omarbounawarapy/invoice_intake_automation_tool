# Pipeline

```
ingest -> mine -> transform -> validate -> serialize
```

`extract_invoice(path)` (in `pipeline.py`) runs the first four stages and
returns a validated `Invoice`; a serializer (`serialize.py`) or the CLI
handles the last one separately, since the same `Invoice` can be
serialized to JSON, CSV, or text without re-running anything upstream.

## 1. Ingest

`pipeline.ingest_invoice_pdf(path)` opens the PDF's first page with
`pdfplumber` and decides which of the two layout ingesters to use: if
`pdfplumber` finds an explicit table on the page, `TableLayoutIngester`
reads line items from it; otherwise `ParagraphLayoutIngester` reads them
as prose between fixed anchor phrases. Both extract the same shape of raw
dict (header, "bill to" address, items, terms, bank, totals, discount) via
a shared `InvoiceIngester` base for the fields that don't depend on
layout.

**Failure mode:** `IngestionError` (a `ValueError` subclass) when the PDF
can't be opened, or an expected anchor/region isn't found on the page.

## 2. Mine

`InvoiceMiner.mine(raw)` (in `mining/invoice_miner.py`) turns that raw
dict into semantically identified fields -- which raw line is a date, a
money amount, a discount, and so on -- normalizing number formats (Swiss
`1'234.56`, German `1.234,56`, plain `1234.56`) and date text into plain
strings along the way. Its own docstring states the contract precisely:
it returns only strings/dicts/lists, never `Decimal`/`date` objects, and
performs no arithmetic, validation, or reconciliation. Anything left
implicit in the source text (an unstated VAT rate, for instance) is left
as `None` here, deliberately, for the transform stage to resolve.

**Failure mode:** `MiningError` (raised as `InvoiceMiningError`, its
existing name, now a subclass) when a required field can't be
semantically identified in the extracted content at all -- as opposed to
being extractable but implicit, which is not an error.

## 3. Transform

`transform.transform_invoice(mined)` converts the miner's strings into
canonical Python types (`Decimal`, `date`) and computes the values the
miner intentionally left implicit: an unstated VAT rate or amount, and a
discount's actual monetary effect. See `docs/data-model.md` for exactly
what gets derived and why.

**Failure mode:** `TransformationError`, carrying the specific field, raw
value, and reason, when a value can't be coerced to its canonical type
(e.g. a non-numeric string where a decimal amount is expected).

## 4. Validate

Validation is not a separate function call -- it happens automatically
when `transform_invoice` constructs the `Invoice` model at the end.
Pydantic enforces field-level constraints (non-empty identifiers,
non-negative amounts, 0-100% rate bounds) and the model's own
cross-field rules (`due_date >= invoice_date`, total sign vs.
credit-note status) at construction time.

**Failure mode:** `pydantic.ValidationError`, which lists every violated
constraint (not just the first one), when the transformed values are
well-typed but violate a structural or business rule.

## 5. Serialize

`serialize.to_json` / `to_csv` / `to_text` take a validated `Invoice` (or
a list, for batch output) and produce the requested output format. This
stage has no failure mode of its own in current use -- it operates on an
already-validated model -- but `errors.OutputError` is reserved for a
future format that can fail independently (e.g. writing to an
unwritable path), so that failure is distinguishable from the four
pipeline stages above rather than surfacing as a generic `OSError`.

## Stage summary

| Stage | Function | Exception |
| --- | --- | --- |
| Ingest | `pipeline.ingest_invoice_pdf` | `IngestionError` |
| Mine | `Miner.mine` | `MiningError` |
| Transform | `transform.transform_invoice` | `TransformationError` |
| Validate | `Invoice(...)` (inside transform_invoice) | `pydantic.ValidationError` |
| Serialize | `serialize.to_*` | `OutputError` (reserved) |
| CLI input | `cli.py` | argparse usage errors, or a plain message for a missing file/directory |

The CLI (`docs/cli.md`) catches all of the above and reports which stage
failed, so a user sees `Error (mining): ...` rather than a bare traceback.

## Known limitation of the layout heuristic

`ingest_invoice_pdf`'s table-vs-paragraph choice is a binary heuristic
(does `pdfplumber` find an explicit table on the page). The project's
reference dataset itself distinguishes a third `mixed` layout category
that this heuristic collapses into whichever of the two extraction paths
happens to work -- see `docs/limitations.md`.
