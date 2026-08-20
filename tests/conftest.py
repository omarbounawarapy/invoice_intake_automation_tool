from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

# Make tests/fixtures/ importable as top-level modules (e.g.
# `from mined_invoices import base_mined_invoice`) without adding a
# src-layout complication for what is test-only helper code.
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))


@pytest.fixture
def example_invoices_dir() -> Path:
    return EXAMPLES_DIR / "invoices"


@pytest.fixture
def example_ground_truth_dir() -> Path:
    return EXAMPLES_DIR / "ground_truth"
