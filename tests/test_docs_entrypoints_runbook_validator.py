from __future__ import annotations

from scripts.validate_docs_entrypoints_runbook import main


def test_validator_docs_entrypoints_runbook_ok():
    assert main() == 0
