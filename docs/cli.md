# CLI reference

```
invoice-tool extract <path> [--format text|json|csv|xlsx] [--output PATH] [--strict]
invoice-tool batch <directory> [--format text|json|csv|xlsx] [--output PATH] [--pattern GLOB] [--strict]
```

## `extract`

Process a single invoice PDF.

```bash
invoice-tool extract examples/invoices/INV-2026-0001.pdf
invoice-tool extract examples/invoices/INV-2026-0001.pdf --format json
invoice-tool extract examples/invoices/INV-2026-0001.pdf --format csv --output result.csv
invoice-tool extract examples/invoices/INV-2026-0001.pdf --format xlsx --output result.xlsx
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--format {text,json,csv,xlsx}` | `text` | Output format. `text` is a human-readable summary; `json` is the full canonical record; `csv`/`xlsx` are one row per line item (`xlsx` also gets an invoice-level summary sheet -- see below). |
| `--output PATH` | stdout | Write to a file instead of printing. **Required for `--format xlsx`** when stdout is an interactive terminal (binary output can still be piped/redirected without it). |
| `--strict` | off | Exit non-zero if the invoice's totals don't reconcile with what the document prints (`consistency != "correct"`), in addition to actual processing failures. |

## `batch`

Process every PDF in a directory.

```bash
invoice-tool batch examples/invoices/
invoice-tool batch examples/invoices/ --format csv --output all_invoices.csv
invoice-tool batch examples/invoices/ --format xlsx --output all_invoices.xlsx
invoice-tool batch examples/invoices/ --pattern "INV-2026-*.pdf"
```

With no `--format`, `batch` prints a one-line status per file plus a
summary count -- useful as a batch job log for many files. `--format
json`/`csv`/`xlsx` instead write the full combined data for every
successfully processed invoice (failures are still reported, to stderr).

A single malformed file does not abort the batch: every other file is
still processed, and the failed one is reported by name and pipeline
stage.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--format {text,json,csv,xlsx}` | `text` | `text` is a per-file summary; `json`/`csv`/`xlsx` combine every successfully processed invoice. |
| `--output PATH` | stdout | Write to a file instead of printing. Required for `--format xlsx` on an interactive terminal (see above). |
| `--pattern GLOB` | `*.pdf` | Which files in the directory to process. |
| `--strict` | off | Exit non-zero if *any* processed invoice has a consistency mismatch (a file that fails to process at all is always non-zero, with or without `--strict`). |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | A file failed to process (see the stage-labeled error message), or `--strict` was given and a consistency mismatch or batch failure occurred. |
| `2` | Argument/usage error (from `argparse` itself -- e.g. an unrecognized `--format` value). |

## Error messages

Errors are reported with the pipeline stage that raised them, e.g.:

```
Error (mining): Cannot mine invoice header: ['...']
Error (transformation): due_date: cannot normalize '2026-13-40' (not a valid ISO date)
Error (validation): 1 validation error for Invoice
  Value error, due_date (2026-01-01) is before invoice_date (2026-02-01) [type=value_error, ...]
```

See `docs/pipeline.md` for what each stage covers.
