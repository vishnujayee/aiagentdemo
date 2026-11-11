import pytest

from dev_run import main as dev_main


def test_dev_flow_runs_without_exception():
    # Run the developer flow; this should complete without raising errors in CI
    # environment where heavy deps are not required (fallbacks used).
    dev_main()
    assert True
