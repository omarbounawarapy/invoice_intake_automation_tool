# Example dataset

Five invoices used throughout this repository's README and as fixtures
for the automated test suite (`tests/integration/test_regression.py`).

```
examples/
├── invoices/       5 source PDFs (INV-2026-0001 .. 0005)
├── ground_truth/   the reference values each PDF was generated from
└── outputs/        real output of `invoice-tool extract`, one per invoice,
                     plus a combined batch.csv
```

The five invoices were deliberately picked to show meaningful variation:

| File               | Layout    | Number format | Discount               | Consistency         |
| ------------------ | --------- | -------------- | ----------------------- | -------------------- |
| `INV-2026-0001.pdf` | table     | english (US)   | 2% percentage            | correct               |
| `INV-2026-0002.pdf` | table     | swiss          | 2% percentage, VAT rate implicit | **total mismatch** |
| `INV-2026-0003.pdf` | paragraph | german         | 2/10 net 30 (conditional, not applied) | correct |
| `INV-2026-0004.pdf` | table     | german         | 2/10 net 30 (conditional, not applied) | **total mismatch** |
| `INV-2026-0005.pdf` | table     | swiss          | flat rebate amount       | correct               |

`ground_truth/INV-2026-0006.json` is included for reference but has **no
matching PDF** in this repository -- it illustrates a *subtotal* mismatch
(the other two mismatch invoices show a *total* mismatch), and is used to
build a synthetic fixture in `tests/fixtures/` since the source PDF isn't
available. See `docs/limitations.md`.

## Regenerating `outputs/`

```bash
for f in examples/invoices/*.pdf; do
    invoice-tool extract "$f" --format json --output "examples/outputs/$(basename "$f" .pdf).json"
    invoice-tool extract "$f" --format text --output "examples/outputs/$(basename "$f" .pdf).txt"
done
invoice-tool batch examples/invoices --format csv --output examples/outputs/batch.csv
```

## Provenance and license

Both the PDFs and their ground-truth values originate from the
[`jngb-labs/InvoiceBenchmark`](https://huggingface.co/datasets/jngb-labs/InvoiceBenchmark)
dataset on Hugging Face (see `scripts/download_dataset.py`, which pulls
the full set). The invoices are **synthetic**: company names, addresses,
IBANs, and transaction details are fictional (several are deliberately
recognizable placeholder names), and no real business or personal data is
involved.

This repository redistributes only the 6 files above as a small,
self-contained example set. We could not independently verify the
dataset's redistribution license from within this environment -- if you
plan to redistribute more of it than these examples, check the dataset
repository directly rather than relying on this note.
