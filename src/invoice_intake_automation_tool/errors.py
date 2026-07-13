"""Shared exception hierarchy for the invoice pipeline.

The pipeline is deliberately split into distinct stages::

    ingest -> mine -> transform -> validate -> serialize

Each stage raises a distinct exception type so a caller (the CLI, a test,
or a client script) can tell *where* a document failed without parsing
error strings. All pipeline exceptions share a common base class so a
caller that only wants to know "did anything go wrong" can catch
``InvoiceToolError`` once.

Field-level *structural* validation (missing required fields, out-of-range
values, impossible date relationships, ...) is handled by Pydantic on the
:class:`~invoice_intake_automation_tool.models.Invoice` model itself and
raises the standard ``pydantic.ValidationError`` -- there is no project
specific wrapper for that stage because Pydantic's error type is already
detailed, standard, and easy to catch.
"""

from __future__ import annotations


class InvoiceToolError(Exception):
    """Base class for all errors raised by this package."""


class IngestionError(InvoiceToolError, ValueError):
    """A source document could not be read, or an expected anchor/region
    could not be located on the page.

    Subclasses ``ValueError`` for backward compatibility with call sites
    that already catch that broad type.
    """


class MiningError(InvoiceToolError, ValueError):
    """Semantic fields could not be identified in the extracted content."""


class TransformationError(InvoiceToolError):
    """A mined value could not be converted to its canonical Python type.

    Carries enough context (which field, which raw value, why) to diagnose
    the failure without re-running the pipeline in a debugger.
    """

    def __init__(self, field: str, value: object, reason: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"{field}: cannot normalize {value!r} ({reason})")


class OutputError(InvoiceToolError):
    """A validated invoice could not be serialized or written to disk."""
