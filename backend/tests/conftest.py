"""Keep backend tests independent from local services and secrets."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.evals.harness_runner import OFFLINE_ENVIRONMENT, clear_runtime_caches


# Set before test modules are imported so cached settings cannot read backend/.env.
os.environ.update(OFFLINE_ENVIRONMENT)


@pytest.fixture(autouse=True)
def isolate_runtime_configuration() -> Iterator[None]:
    clear_runtime_caches()
    try:
        yield
    finally:
        clear_runtime_caches()
