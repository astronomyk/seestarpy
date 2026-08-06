"""Unit tests for the crowdsky.sync() one-call pipeline (crowdsky/__init__.py)."""

from unittest.mock import MagicMock, call, patch

import pytest

from seestarpy import crowdsky
from seestarpy.crowdsky import server


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset server module globals before each test."""
    server.USERNAME = ""
    server.PASSWORD = ""
    server.BASE_URL = "https://crowdsky.univie.ac.at"
    yield


STACK_SUMMARY = {"targets_processed": 2, "total_blocks_stacked": 3}
UPLOAD_SUMMARY = {"files_uploaded": 3, "files_skipped": 1, "files_failed": 0}


def _patched_sync(**kwargs):
    """Run sync() with all I/O patched out; return (result, mocks)."""
    with patch.object(crowdsky.server, "list_stacks", return_value=[]) as m_list, \
            patch.object(crowdsky.chunks, "stack_all",
                         return_value=STACK_SUMMARY) as m_stack, \
            patch.object(crowdsky.server, "upload_all_stacks",
                         return_value=UPLOAD_SUMMARY) as m_upload:
        result = crowdsky.sync(**kwargs)
    return result, m_list, m_stack, m_upload


class TestSync:
    def test_sets_credentials_when_given(self):
        _patched_sync(username="alice", password="s3cret")
        assert server.USERNAME == "alice"
        assert server.PASSWORD == "s3cret"

    def test_keeps_existing_credentials_when_omitted(self):
        server.set_credentials("bob", "hunter2")
        _patched_sync()
        assert server.USERNAME == "bob"
        assert server.PASSWORD == "hunter2"

    @pytest.mark.parametrize("kwargs", [
        {"username": "alice"},
        {"password": "s3cret"},
    ])
    def test_partial_credentials_raise(self, kwargs):
        with pytest.raises(ValueError, match="both username and password"):
            crowdsky.sync(**kwargs)

    def test_returns_combined_summary(self):
        result, *_ = _patched_sync(username="alice", password="s3cret")
        assert result == {"stack": STACK_SUMMARY, "upload": UPLOAD_SUMMARY}

    def test_stacks_before_uploading(self):
        order = []
        with patch.object(crowdsky.server, "list_stacks", return_value=[]), \
                patch.object(crowdsky.chunks, "stack_all",
                             side_effect=lambda **kw: order.append("stack")), \
                patch.object(crowdsky.server, "upload_all_stacks",
                             side_effect=lambda **kw: order.append("upload")):
            crowdsky.sync(username="alice", password="s3cret")
        assert order == ["stack", "upload"]

    def test_bad_credentials_fail_before_stacking(self):
        with patch.object(crowdsky.server, "list_stacks",
                          side_effect=RuntimeError("authentication failed")), \
                patch.object(crowdsky.chunks, "stack_all") as m_stack:
            with pytest.raises(RuntimeError, match="authentication failed"):
                crowdsky.sync(username="alice", password="wrong")
        m_stack.assert_not_called()

    def test_kwargs_passed_through(self):
        _, _, m_stack, m_upload = _patched_sync(
            username="alice", password="s3cret", dest="./dl",
            block_minutes=30, min_exptime=120, skip_existing=False,
            dry_run=True, max_wait_sec=600,
        )
        m_stack.assert_called_once_with(
            block_minutes=30, min_exptime=120, dry_run=True, max_wait_sec=600)
        m_upload.assert_called_once_with(
            dest="./dl", skip_existing=False, dry_run=True)
