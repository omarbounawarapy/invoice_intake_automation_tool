# Contributing

Thanks for considering a contribution to Invoice Intake Automation Tool.

## Getting set up

```bash
git clone https://github.com/omarbounawarapy/invoice_intake_automation_tool.git
cd invoice_intake_automation_tool
pip install -e ".[dev]"
pytest
```

Requires Python 3.12+.

## Before opening a pull request

- Add or update tests for any behavior change. The suite is split into
  `tests/unit/`, `tests/integration/`, and `tests/integration/test_regression.py`
  (see [`README.md`](README.md#testing) for what each layer covers).
- Run `pytest` locally; CI runs the same suite on every push and PR.
- Keep the layering in `src/invoice_intake_automation_tool/` intact:
  ingestion, mining, transformation, and the canonical `Invoice` model
  are separate stages with separate responsibilities (see
  [`docs/architecture.md`](docs/architecture.md)). Changes that blur
  those boundaries will likely be asked to be split up.
- Monetary values must stay `Decimal`, never `float` (see
  [Design decisions](README.md#design-decisions) in the README for why).
- Update the relevant doc under `docs/` if you change public behavior
  (CLI flags, output schema, supported formats).

## Reporting bugs / requesting features

Open a GitHub issue. For a bug, include the invoice layout/number format
involved if relevant (without sharing real financial data — use a
redacted or synthetic sample, similar to `examples/invoices/`).

## Scope

This project is intentionally narrow: text-layer PDF invoices, not OCR
or full accounting/compliance. See [`docs/limitations.md`](docs/limitations.md)
before proposing a feature that falls outside that scope.
