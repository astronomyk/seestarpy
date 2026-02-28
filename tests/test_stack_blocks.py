"""Unit tests for CrowdSky time-block stacking functions in crowdsky.py."""

from datetime import datetime
from unittest.mock import patch

import pytest

from seestarpy.crowdsky import (
    _floor_to_block,
    _parse_light_filename,
    find_unstacked_blocks,
    list_targets,
)


# ---------------------------------------------------------------------------
# _parse_light_filename
# ---------------------------------------------------------------------------

class TestParseLightFilename:
    def test_standard_filename(self):
        result = _parse_light_filename(
            "Light_M 81_20.0s_LP_20260227-225203.fit"
        )
        assert result == {
            "target": "M 81",
            "exposure": "20.0s",
            "filter": "LP",
            "datetime": datetime(2026, 2, 27, 22, 52, 3),
        }

    def test_ircut_filter(self):
        result = _parse_light_filename(
            "Light_M 81_10.0s_IRCUT_20250607-221746.fit"
        )
        assert result["filter"] == "IRCUT"
        assert result["exposure"] == "10.0s"

    def test_complex_target_name(self):
        result = _parse_light_filename(
            "Light_NGC 2244 Satellite Cluster_10.0s_LP_20260227-225203.fit"
        )
        assert result["target"] == "NGC 2244 Satellite Cluster"

    def test_target_with_underscore(self):
        result = _parse_light_filename(
            "Light_Some_Target_20.0s_LP_20260227-225203.fit"
        )
        assert result["target"] == "Some_Target"

    def test_non_matching_returns_none(self):
        assert _parse_light_filename("random_file.jpg") is None
        assert _parse_light_filename("DSO_Stacked_38_M 81_20.0s_20260227_225203.fit") is None
        assert _parse_light_filename("Light_M 81_20.0s_LP_20260227-225203.jpg") is None

    def test_thumbnail_not_matched(self):
        assert _parse_light_filename(
            "Light_M 81_20.0s_LP_20260227-225203_thn.jpg"
        ) is None


# ---------------------------------------------------------------------------
# _floor_to_block
# ---------------------------------------------------------------------------

class TestFloorToBlock:
    def test_mid_block(self):
        dt = datetime(2026, 2, 27, 22, 52, 3)
        assert _floor_to_block(dt, 15) == datetime(2026, 2, 27, 22, 45, 0)

    def test_on_boundary(self):
        dt = datetime(2026, 2, 27, 23, 0, 0)
        assert _floor_to_block(dt, 15) == datetime(2026, 2, 27, 23, 0, 0)

    def test_just_after_boundary(self):
        dt = datetime(2026, 2, 27, 23, 0, 1)
        assert _floor_to_block(dt, 15) == datetime(2026, 2, 27, 23, 0, 0)

    def test_30_minute_blocks(self):
        dt = datetime(2026, 2, 27, 22, 52, 0)
        assert _floor_to_block(dt, 30) == datetime(2026, 2, 27, 22, 30, 0)

    def test_microseconds_cleared(self):
        dt = datetime(2026, 2, 27, 22, 52, 3, 500000)
        result = _floor_to_block(dt, 15)
        assert result.microsecond == 0


# ---------------------------------------------------------------------------
# find_unstacked_blocks
# ---------------------------------------------------------------------------

def _make_light_files(target, exposure, filt, times):
    """Helper to generate Light_ filenames from a list of (HH, MM, SS)."""
    files = {}
    for h, m, s in times:
        fname = f"Light_{target}_{exposure}_{filt}_20260227-{h:02d}{m:02d}{s:02d}.fit"
        files[fname] = 4050000  # dummy size
    return files


class TestFindUnstackedBlocks:
    @patch("seestarpy.crowdsky.data")
    def test_basic_grouping(self, mock_data):
        """Frames in two 15-min blocks should produce two blocks."""
        raw = _make_light_files("M 81", "20.0s", "LP", [
            # Block 22:45
            (22, 45, 10), (22, 50, 20), (22, 55, 30),
            # Block 23:00
            (23, 0, 10), (23, 5, 20), (23, 10, 30),
        ])
        mock_data.list_folder_contents.side_effect = [
            raw,       # raw files from _sub folder
            {},        # stacked files from main folder
        ]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        assert len(blocks) == 2
        assert blocks[0]["block_start"] == datetime(2026, 2, 27, 22, 45, 0)
        assert blocks[0]["frame_count"] == 3
        assert blocks[1]["block_start"] == datetime(2026, 2, 27, 23, 0, 0)
        assert blocks[1]["frame_count"] == 3

    @patch("seestarpy.crowdsky.data")
    def test_current_block_skipped(self, mock_data):
        """The current (incomplete) block should be excluded."""
        raw = _make_light_files("M 81", "20.0s", "LP", [
            (22, 45, 10), (22, 50, 20),
        ])
        mock_data.list_folder_contents.side_effect = [raw, {}]

        # "now" is within the 22:45 block
        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 27, 22, 55, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        assert len(blocks) == 0

    @patch("seestarpy.crowdsky.data")
    def test_covered_block_excluded(self, mock_data):
        """Blocks with matching CrowdSky output files should be excluded.

        CrowdSky filenames encode the block-start timestamp and filter
        for exact coverage matching.
        """
        raw = _make_light_files("M 81", "20.0s", "LP", [
            (22, 45, 10), (22, 50, 20), (22, 55, 30),
            (23, 0, 10), (23, 5, 20),
        ])
        stacked = {
            # CrowdSky file covers the 22:45 block exactly
            "CrowdSky_3_M 81_20.0s_LP_20260227-224500.fit": 10000,
        }
        mock_data.list_folder_contents.side_effect = [raw, stacked]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        # The 22:45 block is covered; 23:00 block (2 frames) remains
        assert len(blocks) == 1
        assert blocks[0]["block_start"] == datetime(2026, 2, 27, 23, 0, 0)

    @patch("seestarpy.crowdsky.data")
    def test_dso_stacked_does_not_mark_coverage(self, mock_data):
        """Plain DSO_Stacked files should NOT mark coverage."""
        raw = _make_light_files("M 81", "20.0s", "LP", [
            (22, 45, 10), (22, 50, 20), (22, 55, 30),
        ])
        stacked = {
            # DSO_Stacked (not CrowdSky) — should be ignored for coverage
            "DSO_Stacked_3_M 81_20.0s_20260228_205636.fit": 10000,
        }
        mock_data.list_folder_contents.side_effect = [raw, stacked]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        # Block should NOT be covered — only CrowdSky files count
        assert len(blocks) == 1
        assert blocks[0]["block_start"] == datetime(2026, 2, 27, 22, 45, 0)

    @patch("seestarpy.crowdsky.data")
    def test_crowdsky_exact_match_handles_duplicate_frame_counts(self, mock_data):
        """CrowdSky coverage is by block timestamp, not frame count."""
        raw = _make_light_files("M 81", "20.0s", "LP", [
            # Block 22:45 — 3 frames
            (22, 45, 10), (22, 50, 20), (22, 55, 30),
            # Block 23:00 — also 3 frames
            (23, 0, 10), (23, 5, 20), (23, 10, 30),
        ])
        stacked = {
            # Only the 22:45 block is covered (exact timestamp match)
            "CrowdSky_3_M 81_20.0s_LP_20260227-224500.fit": 10000,
        }
        mock_data.list_folder_contents.side_effect = [raw, stacked]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        # Only the 23:00 block remains — exact match, no ambiguity
        assert len(blocks) == 1
        assert blocks[0]["block_start"] == datetime(2026, 2, 27, 23, 0, 0)

    @patch("seestarpy.crowdsky.data")
    def test_mixed_exposure_filter_subgroups(self, mock_data):
        """Frames with different exposure/filter combos produce sub-blocks."""
        raw = {
            **_make_light_files("M 81", "20.0s", "LP", [(22, 45, 10), (22, 50, 20)]),
            **_make_light_files("M 81", "10.0s", "IRCUT", [(22, 46, 0), (22, 51, 0)]),
        }
        mock_data.list_folder_contents.side_effect = [raw, {}]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        assert len(blocks) == 2
        exposures = {b["exposure"] for b in blocks}
        assert exposures == {"20.0s", "10.0s"}
        filters = {b["filter"] for b in blocks}
        assert filters == {"LP", "IRCUT"}

    @patch("seestarpy.crowdsky.data")
    def test_no_raw_files_returns_empty(self, mock_data):
        mock_data.list_folder_contents.return_value = {}
        blocks = find_unstacked_blocks("M 81")
        assert blocks == []

    @patch("seestarpy.crowdsky.data")
    def test_files_sorted_within_block(self, mock_data):
        """Files within a block should be sorted by filename (chronological)."""
        raw = _make_light_files("M 81", "20.0s", "LP", [
            (22, 55, 30), (22, 45, 10), (22, 50, 20),
        ])
        mock_data.list_folder_contents.side_effect = [raw, {}]

        with patch("seestarpy.crowdsky.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 28, 12, 0, 0)
            mock_dt.strptime = datetime.strptime
            blocks = find_unstacked_blocks("M 81")

        assert len(blocks) == 1
        # Files should be sorted
        for i in range(len(blocks[0]["files"]) - 1):
            assert blocks[0]["files"][i] < blocks[0]["files"][i + 1]


# ---------------------------------------------------------------------------
# list_targets
# ---------------------------------------------------------------------------

class TestListTargets:
    @patch("seestarpy.crowdsky.data")
    def test_finds_target_pairs(self, mock_data):
        mock_data.list_folders.return_value = {
            "M 81": 3,
            "M 81_sub": 1052,
            "Lunar": 2,
            "M 42": 1,
            "M 42_sub": 500,
        }
        targets = list_targets()
        assert len(targets) == 2
        assert targets[0]["target"] == "M 42"
        assert targets[0]["raw_files"] == 500
        assert targets[0]["stacked_files"] == 1
        assert targets[1]["target"] == "M 81"

    @patch("seestarpy.crowdsky.data")
    def test_orphan_sub_folder_excluded(self, mock_data):
        """A _sub folder without a matching main folder is not a target."""
        mock_data.list_folders.return_value = {
            "Orphan_sub": 100,
            "M 81": 3,
            "M 81_sub": 500,
        }
        targets = list_targets()
        assert len(targets) == 1
        assert targets[0]["target"] == "M 81"

    @patch("seestarpy.crowdsky.data")
    def test_empty_returns_empty(self, mock_data):
        mock_data.list_folders.return_value = {}
        assert list_targets() == []
