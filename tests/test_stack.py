"""Unit tests for the batch-stack JSON-RPC wrappers in stack.py.

These assert the exact payload shape sent to the firmware, in particular the
firmware v7.75 requirement that each file entry carries a full relative path
from the SD-card root (bare filenames make the firmware fail with
``state="fail"``, ``error="no image"``, ``code=267``).
"""

from unittest.mock import patch

from seestarpy import stack


class TestSetBatchStackSetting:
    @patch("seestarpy.stack.send_command")
    def test_bare_filenames_get_full_path(self, mock_send):
        """Bare filenames are prefixed with *path* (v7.75 requirement)."""
        stack.set_batch_stack_setting(
            "MyWorks/NGC 7000_sub",
            [
                "Light_NGC 7000_20.0s_IRCUT_20260613-225623.fit",
                "Light_NGC 7000_20.0s_IRCUT_20260613-225644.fit",
            ],
        )
        sent = mock_send.call_args[0][0]
        assert sent["method"] == "set_batch_stack_setting"
        assert sent["params"]["path"] == "MyWorks/NGC 7000_sub"
        names = [f["name"] for f in sent["params"]["files"]]
        assert names == [
            "MyWorks/NGC 7000_sub/Light_NGC 7000_20.0s_IRCUT_20260613-225623.fit",
            "MyWorks/NGC 7000_sub/Light_NGC 7000_20.0s_IRCUT_20260613-225644.fit",
        ]

    @patch("seestarpy.stack.send_command")
    def test_full_paths_passed_through(self, mock_send):
        """Entries already containing a '/' are left untouched (idempotent)."""
        full = "MyWorks/M 81_sub/Light_M 81_10.0s_LP_20260120-061408.fit"
        stack.set_batch_stack_setting("MyWorks/M 81_sub", [full])
        sent = mock_send.call_args[0][0]
        assert [f["name"] for f in sent["params"]["files"]] == [full]

    @patch("seestarpy.stack.send_command")
    def test_empty_file_list(self, mock_send):
        stack.set_batch_stack_setting("MyWorks/M 81_sub", [])
        sent = mock_send.call_args[0][0]
        assert sent["params"]["files"] == []


class TestClearBatchStack:
    @patch("seestarpy.stack.send_command")
    def test_uses_direct_method_first(self, mock_send):
        """v7.75 firmware: the direct clear_batch_stack method is used."""
        mock_send.return_value = {"code": 0, "result": 0}
        stack.clear_batch_stack()
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0] == {"method": "clear_batch_stack"}

    @patch("seestarpy.stack.send_command")
    def test_falls_back_on_code_103(self, mock_send):
        """Old firmware: code 103 triggers the clear_app_state fallback."""
        mock_send.side_effect = [
            {"code": 103, "error": "method not found"},
            {"code": 0, "result": 0},
        ]
        stack.clear_batch_stack()
        assert mock_send.call_count == 2
        assert mock_send.call_args_list[0][0][0] == {"method": "clear_batch_stack"}
        assert mock_send.call_args_list[1][0][0] == {
            "method": "clear_app_state",
            "params": {"name": "BatchStack"},
        }

    @patch("seestarpy.stack.send_command")
    def test_no_fallback_when_recognised(self, mock_send):
        """A non-103 reply (e.g. code 0) does not trigger the fallback."""
        mock_send.return_value = {"code": 0}
        stack.clear_batch_stack()
        mock_send.assert_called_once()
