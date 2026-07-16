# Data model

The canonical output of this project is one Pydantic model,
`invoice_intake_automation_tool.models.Invoice`. This document explains
every field and, where the reason isn't obvious, why it works the way it
does. For the code, see `src/invoice_intake_automation_tool/models/`.

## Field reference

| Field | Type | Notes |
| --- | --- | --- |
| `invoice_id` | `str` | required |
| `is_credit_note` | `bool` | default `False` |
| `source_file` | `str \| None` | set by the pipeline, not mined from the document |
| `vendor` / `recipient` | `str` | required |
| `vendor_country` / `recipient_country` | `str \| None` | ISO country code where determinable |
| `vendor_address` / `recipient_address` | `Address` | `street` required; `postal_code`/`city` optional |
| `invoice_date` | `date` | required |
| `due_date` | `date \| None` | must not be before `invoice_date` |
| `line_items` | `list[LineItem]` | at least one required |
| `currency` | `str \| None` | 3-letter code when known |
| `vat_rate` | `Decimal \| None` | 0-1 fraction; stated or derived (below) |
| `vat_amount` | `Decimal` | always present; stated or derived |
| `discount` | `Discount \| None` | the *offer*, not its monetary effect |
| `discount_amount` | `Decimal` | the actual effect; 0 for a conditional, unapplied discount |
| `subtotal` | `Decimal` | **computed**, not settable -- sum of `line_items[].amount` |
| `total` | `Decimal` | **computed** -- `subtotal - discount_amount + vat_amount` |
| `rendered_subtotal` / `rendered_total` | `Decimal` | what the document literally prints, for comparison |
| `consistency` | `ConsistencyStatus` | **computed** -- see below |
| `consistency_note` | `str \| None` | **computed** -- human-readable explanation of any mismatch |
| `payment_terms` | `str \| None` | free text |
| `bank_details` | `str \| None` | one opaque string; see "Why not structured IBAN/BIC fields?" |
| `layout` / `number_format` / `vat_variant` / `discount_variant` / `edge_case` | `str \| None` | free-form diagnostic tags from the mining layer |

## Why `subtotal` and `total` are computed, not stored

`subtotal` is defined as the sum of `line_items[].amount`, full stop --
not as "the number the mining layer found near the word 'subtotal'".
`total` is defined as `subtotal - discount_amount + vat_amount`. Both are
implemented as Pydantic `computed_field` properties, so they cannot be
passed to the constructor and cannot silently disagree with the data they
are derived from: `Invoice(..., subtotal=<anything>)` is a
`pydantic.ValidationError` (extra fields are forbidden), not a value that
gets accepted and then ignored.

This matters because a real invoice's *printed* subtotal/total can simply
be wrong -- two of this project's five example invoices have a printed
total that doesn't match their own line items (see `examples/README.md`).
Making `subtotal`/`total` a function of the line items rather than a
copy of the printed figure is what makes it possible to both (a) report
the correct total and (b) detect that the document disagrees with it, in
the same field, without a "which number is real" ambiguity.

## The accounting assumption this project makes explicit

`total = subtotal - discount_amount + vat_amount` assumes discounts apply
to the (VAT-exclusive) subtotal and VAT is added on top of the
post-discount amount. This held for every internally-consistent invoice in
the project's reference dataset, *including* one whose document text
described VAT as "included" (`vat_variant: explicit_included` in
`examples/ground_truth/INV-2026-0006.json`) -- the canonical schema
normalizes to a net-subtotal-plus-VAT convention regardless of how the
source text phrases it. Similarly, `discount.applied_to` is always
observed as `"subtotal"` in this project's data; the tool does not attempt
to handle a discount applied to a different base.

## Consistency checking

`consistency` compares the computed `subtotal`/`total` against
`rendered_subtotal`/`rendered_total` (what the page actually prints),
within a `Decimal("0.01")` tolerance for rounding noise:

| Status | Meaning |
| --- | --- |
| `correct` | rendered figures match computed figures |
| `subtotal_error` | only the rendered subtotal disagrees |
| `total_error` | only the rendered total disagrees |
| `multiple_errors` | both disagree |

This is diagnostic metadata, not a rejection -- constructing an `Invoice`
never fails because of a consistency mismatch. A source document being
internally inconsistent is a fact worth reporting to the person using this
tool, not a reason to withhold the rest of the (still perfectly
extractable) data. See `docs/limitations.md` for what this check does and
does not cover.

## VAT and discount derivation

The mining layer intentionally leaves some values implicit when the
source document does (see `docs/pipeline.md`); the transform layer
resolves them:

* **VAT rate stated, amount not** -- amount is derived as
  `subtotal * rate`.
* **VAT amount stated, rate not** (the `implicit_no_rate` case, e.g. "Net
  prices. Statutory VAT applies." with no percentage anywhere) -- rate is
  derived as `amount / subtotal`. The derived rate is then back-filled
  onto any line item that didn't state its own rate, so a client reading
  `line_items[].vat_rate` doesn't need to know the derivation happened.
* **Neither stated** -- amount defaults to `0.00`, correct for exempt /
  reverse-charge invoices and otherwise surfaced for review via
  `vat_variant` rather than guessed.
* **Discount amount** is computed from `discount.type`/`value` and the
  computed `subtotal`, not read off the page: a `percentage` or
  `trade_terms` discount's `value` is a rate (`subtotal * value`); an
  `amount` discount's `value` is already the absolute figure. A
  `conditional` discount (early-payment trade terms the tool cannot
  confirm was taken) always contributes `0.00`, with the offer itself
  still visible via the `discount` field.

## Why some fields are `None` instead of `""`

Extraction can fail to find a value in two different ways: the field is
genuinely absent from the document, or the document has it but the
extraction logic couldn't isolate it cleanly (e.g. an address block with
no separately-formatted postal code). Both used to collapse to `""` from
the mining layer. The transform layer normalizes blank strings to `None`
everywhere so a caller can tell "not found" apart from "confirmed empty"
-- `country`, address parts, `currency`, `payment_terms`, `bank_details`,
and every other optional string field follow this rule.

## Why diagnostic tags are plain strings, not an enum

`layout`, `number_format`, `vat_variant`, `discount_variant`, and
`edge_case` come straight from the mining layer's own (larger) tag
vocabulary. This repository's fixture set only demonstrates a handful of
values for each; a closed `Literal`/`Enum` type would reject a legitimate
tag it simply hasn't seen yet. `consistency` *is* a closed `Enum` because
this project's own transform layer, not the miner, fully controls its
four possible values.

## Why not structured IBAN/BIC fields?

The mining layer's public output only exposes a single `bank_details`
string (this mirrors the project's reference ground truth, which also
uses one string). It has private logic that parses IBAN/BIC internally
(used to infer `vendor_country`), but does not yet publish the breakdown,
and reimplementing that parsing outside the mining module would blur the
extraction/normalization boundary described in `docs/architecture.md`.
Exposing structured banking fields is listed as a future improvement in
the README.

## Credit notes

`is_credit_note` is mined from the document header. The one place it
currently changes validation behavior is the sign of `total`: a negative
total is rejected for an ordinary invoice (it would indicate, for
example, a discount larger than the pre-discount amount) but allowed for
a credit note. Line item amounts remain non-negative regardless -- no
credit-note example was available in this project's reference data to
confirm the sign convention real source documents use for individual
lines, so the tool does not guess one (`docs/limitations.md`).
