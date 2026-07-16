"""Invoice Intake Automation Tool.

Extracts, normalizes, and validates structured data from semi-structured
invoice PDFs into a canonical, typed :class:`Invoice` record.

Public API::

    from invoice_intake_automation_tool import extract_invoice

    invoice = extract_invoice("invoice.pdf")
    print(invoice.total, invoice.consistency)

See ``docs/architecture.md`` for how ``extract_invoice`` is composed from
the pipeline's ingest -> mine -> transform -> validate stages, and
``docs/data-model.md`` for the full field reference.
"""

from .errors import IngestionError, InvoiceToolError, MiningError, OutputError, TransformationError
from .models import Address, ConsistencyStatus, Discount, DiscountType, Invoice, LineItem
from .pipeline import BatchResult, extract_invoice, extract_invoice_batch

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # pipeline
    "extract_invoice",
    "extract_invoice_batch",
    "BatchResult",
    # canonical models
    "Invoice",
    "LineItem",
    "Address",
    "Discount",
    "DiscountType",
    "ConsistencyStatus",
    # errors
    "InvoiceToolError",
    "IngestionError",
    "MiningError",
    "TransformationError",
    "OutputError",
]
