"""Unit tests for _rename_output robustness in crowdsky/chunks.py.

These cover the idempotency-critical behaviour: the .fit rename must be
treated as fatal on failure (so the block is reported as not covered and
re-stacked), while .jpg/_thn.jpg companions are best-effort.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from seestarpy.crowdsky import chunks


class _FakeSMB:
    """Minimal stand-in for a pysmb SMBConnection."""

    def __init__(self, fail_on=()):  # fail_on: iterable of filename suffixes
        self.fail_on = tuple(fail_on)
        self.renamed = []
        self.closed = False

    def rename(self, share, src, dst):
        if any(src.endswith(sfx) for sfx in self.fail_on):
            raise RuntimeError(f"no such file: {src}")
        self.renamed.append((src, dst))

    def close(self):
        self.closed = True


def _block():
    return {
        "block_start": datetime(2026, 3, 11, 21, 35, 0),
        "block_end": datetime(2026, 3, 11, 21, 50, 0),
        "exposure": "20.0s",
        "filter": "LP",
        "frame_count": 12,
    }


def _status(files=None):
    if files is None:
        files = [
            {"name": "DSO_Stacked_12_M 81_20.0s_20260311_213509.fit"},
            {"name": "DSO_Stacked_12_M 81_20.0s_20260311_213509_thn.jpg"},
        ]
    return {"output_file": {"path": "MyWorks/M 81", "files": files}}


@pytest.fixture
def _fixed_chunk_key():
    with patch.object(chunks, "compute_chunk_key",
                      return_value="20260311.77_HP012345"):
        yield


class TestRenameOutput:
    def test_success_renames_fit_and_companions(self, _fixed_chunk_key):
        fake = _FakeSMB()
        with patch.object(chunks, "_read_fits_ra_dec", return_value=(10.0, 20.0)), \
             patch.object(chunks.data, "_connect_smb", return_value=fake):
            out = chunks._rename_output("M 81", _block(), _status())

        assert out == "CrowdSky_12_M 81_20.0s_LP_20260311.77_HP012345.fit"
        renamed_exts = [dst.rsplit("/", 1)[-1] for _, dst in fake.renamed]
        # .fit + .jpg + _thn.jpg all attempted
        assert any(n.endswith(".fit") for n in renamed_exts)
        assert any(n.endswith("_thn.jpg") for n in renamed_exts)
        assert fake.closed is True

    def test_no_output_file_returns_none(self):
        out = chunks._rename_output("M 81", _block(),
                                    {"output_file": {"files": []}})
        assert out is None

    def test_no_fit_returns_none(self):
        status = _status(files=[{"name": "something_thn.jpg"}])
        out = chunks._rename_output("M 81", _block(), status)
        assert out is None

    def test_fit_rename_failure_is_fatal(self, _fixed_chunk_key, capsys):
        """If the .fit rename fails, return None and don't touch companions."""
        fake = _FakeSMB(fail_on=(".fit",))
        with patch.object(chunks, "_read_fits_ra_dec", return_value=(10.0, 20.0)), \
             patch.object(chunks.data, "_connect_smb", return_value=fake):
            out = chunks._rename_output("M 81", _block(), _status())

        assert out is None
        assert fake.renamed == []          # companions never attempted
        assert fake.closed is True
        assert "re-stacked" in capsys.readouterr().out

    def test_missing_companion_is_tolerated(self, _fixed_chunk_key):
        """A missing .jpg/_thn.jpg must not undo a good .fit rename."""
        fake = _FakeSMB(fail_on=(".jpg",))  # both .jpg and _thn.jpg end in .jpg
        with patch.object(chunks, "_read_fits_ra_dec", return_value=(10.0, 20.0)), \
             patch.object(chunks.data, "_connect_smb", return_value=fake):
            out = chunks._rename_output("M 81", _block(), _status())

        assert out == "CrowdSky_12_M 81_20.0s_LP_20260311.77_HP012345.fit"
        assert len(fake.renamed) == 1       # only the .fit succeeded
        assert fake.renamed[0][0].endswith(".fit")

    def test_smb_connect_failure_returns_none(self, _fixed_chunk_key, capsys):
        with patch.object(chunks, "_read_fits_ra_dec", return_value=(10.0, 20.0)), \
             patch.object(chunks.data, "_connect_smb",
                          side_effect=ConnectionError("down")):
            out = chunks._rename_output("M 81", _block(), _status())

        assert out is None
        assert "re-stacked" in capsys.readouterr().out

    def test_missing_radec_warns_and_uses_placeholder(self, capsys):
        """A failed RA/Dec read warns and falls back to HP000000."""
        fake = _FakeSMB()
        with patch.object(chunks, "_read_fits_ra_dec", return_value=(None, None)), \
             patch.object(chunks.data, "_connect_smb", return_value=fake):
            out = chunks._rename_output("M 81", _block(), _status())

        assert out is not None
        assert out.endswith("_HP000000.fit")
        assert "HP000000" in capsys.readouterr().out
