from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    marker_expression = config.option.markexpr or ""
    run_integration = marker_expression.strip() == "integration"
    if run_integration:
        return

    skip_integration = pytest.mark.skip(
        reason="integration tests require explicit selection with -m integration"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
