"""File discovery: lock files, duplicates, and loud failure on real corruption."""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from pricecast import ingest
from pricecast.config import RAW_DIR

REAL_EXPORT = RAW_DIR / "Final_Maize.xls"


@pytest.fixture
def raw_dir(tmp_path) -> Path:
    """A raw directory holding one genuine export."""
    target = tmp_path / "raw"
    target.mkdir()
    shutil.copy(REAL_EXPORT, target / "Final_Maize.xls")
    return target


def test_libreoffice_lock_file_is_skipped(raw_dir):
    """'.~Final_Maize.xls' is committed on main and matches a *.xls glob."""
    (raw_dir / ".~Final_Maize.xls").write_bytes(b"\x05outis" + b"\x00" * 150)
    usable, skipped = ingest.discover_exports(raw_dir)
    assert [p.name for p in usable] == ["Final_Maize.xls"]
    assert [p.name for p in skipped] == [".~Final_Maize.xls"]


def test_excel_lock_file_is_skipped(raw_dir):
    (raw_dir / "~$Final_Maize.xls").write_bytes(b"\x00" * 165)
    usable, skipped = ingest.discover_exports(raw_dir)
    assert [p.name for p in usable] == ["Final_Maize.xls"]
    assert [p.name for p in skipped] == ["~$Final_Maize.xls"]


def test_load_all_survives_a_lock_file(raw_dir):
    """Before the guard this crashed openpyxl and aborted the whole ingest."""
    (raw_dir / ".~Final_Maize.xls").write_bytes(b"\x05outis" + b"\x00" * 150)
    obs, reports = ingest.load_all(raw_dir, aliases_path=None)
    assert len(reports) == 1
    assert not obs.empty


def test_corrupt_export_fails_loudly(raw_dir):
    """A genuinely unreadable data file must not be silently skipped."""
    (raw_dir / "Broken_Export.xls").write_bytes(b"not a spreadsheet at all")
    with pytest.raises(RuntimeError, match="Broken_Export.xls"):
        ingest.load_all(raw_dir, aliases_path=None)


def test_double_extension_file_is_ingested_once(tmp_path):
    """main shipped 'Final_Onions.xls.xls'; the glob must not double-count it."""
    target = tmp_path / "raw"
    target.mkdir()
    shutil.copy(REAL_EXPORT, target / "Final_Maize.xls.xls")
    usable, _ = ingest.discover_exports(target)
    assert len(usable) == 1
    obs, reports = ingest.load_all(target, aliases_path=None)
    assert len(reports) == 1
    assert not obs.duplicated(subset=ingest.KEY_COLS).any()


def test_empty_directory_is_an_explicit_error(tmp_path):
    empty = tmp_path / "raw"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no readable"):
        ingest.load_all(empty, aliases_path=None)


def test_shipped_raw_directory_is_clean_and_loadable():
    """Guards the actual repo contents, not a synthetic fixture."""
    usable, skipped = ingest.discover_exports(RAW_DIR)
    assert not skipped, f"lock files present in data/raw: {[p.name for p in skipped]}"
    assert len(usable) >= 8
    names = {p.name for p in usable}
    assert {"Final_Maize.xls", "Final_Cabbages.xls", "Final_Tomatoes.xls",
            "Final_Onions_2024-2026.xls"} <= names


def test_current_era_files_cover_all_four_live_crops():
    """The fresh exports merged from main must actually be current."""
    frames = []
    for name in ("Final_Maize.xls", "Final_Cabbages.xls", "Final_Tomatoes.xls",
                 "Final_Onions_2024-2026.xls"):
        agg, report = ingest.load_export(RAW_DIR / name)
        frames.append((report.commodity, report.date_max))
    for commodity, date_max in frames:
        assert pd.Timestamp(date_max) >= pd.Timestamp("2026-01-01"), (
            f"{commodity} export is not current: ends {date_max}"
        )
