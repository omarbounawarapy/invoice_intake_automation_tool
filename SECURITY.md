# Security Policy

## Supported versions

This project is pre-1.0 (currently `0.1.0`). Security fixes are made
against the `main` branch only; there is no back-porting to older
versions yet.

## Reporting a vulnerability

Please report security issues privately rather than opening a public
GitHub issue. Use GitHub's
[private vulnerability reporting](https://github.com/omarbounawarapy/invoice_intake_automation_tool/security/advisories/new)
for this repository.

Include:

- A description of the issue and its potential impact.
- Steps to reproduce, or a minimal example invoice/input if the issue is
  triggered by parsing a specific document.

## Scope notes

This tool parses untrusted PDF files (via `pdfplumber`) and writes files
locally (JSON/CSV/XLSX). Reports involving how it handles malformed or
adversarial PDF input are in scope. This is not accounting or compliance
software and makes no guarantees about extraction correctness beyond
what's documented in [`docs/limitations.md`](docs/limitations.md); such
gaps should be filed as ordinary bug reports, not security issues, unless
they represent an actual security impact (e.g. crash, resource
exhaustion, arbitrary file write).
