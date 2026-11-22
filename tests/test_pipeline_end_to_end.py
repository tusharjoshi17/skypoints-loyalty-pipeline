"""Runs the whole pipeline on the sample feeds shipped in data/input."""

import csv
import shutil
from pathlib import Path

import pytest

from skypoints.pipeline import run

INPUT = Path(__file__).resolve().parents[1] / "data" / "input"


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def member_files():
    return sorted(INPUT.glob("SKYPOINTS_MEMBERS_*.txt"))


def redemption_files():
    return sorted(INPUT.glob("SKYPOINTS_REDEMPTIONS_*.json"))


@pytest.fixture
def summary_and_output(tmp_path):
    return run(member_files(), redemption_files(), tmp_path), tmp_path


def test_every_row_read_is_accounted_for(summary_and_output):
    summary, _ = summary_and_output

    assert summary.is_reconciled
    assert summary.detail_rows_read == 12


def test_member_who_moved_lives_only_in_the_new_country(summary_and_output):
    summary, out = summary_and_output

    india = {row.get("member_id") for row in read_csv(out / "targets" / "TABLE_INDIA.csv")}
    usa = {row.get("member_id") for row in read_csv(out / "targets" / "TABLE_USA.csv")}

    assert ("223458", "IND", "USA") in summary.moves
    assert "223458" in usa
    assert "223458" not in india


def test_no_member_appears_in_two_country_tables(summary_and_output):
    _, out = summary_and_output

    ids = [row.get("member_id") for f in (out / "targets").glob("*.csv") for row in read_csv(f)]

    assert len(ids) == len(set(ids))


def test_quarantined_rows_never_reach_country_tables(summary_and_output):
    _, out = summary_and_output

    rejected = {row.get("member_name") for row in read_csv(out / "quarantine" / "member_rejects.csv")}
    loaded = {row.get("member_name") for f in (out / "targets").glob("*.csv") for row in read_csv(f)}

    assert rejected == {"Liam", "Omar"}
    assert not rejected & loaded


def test_rerunning_the_same_files_is_idempotent(tmp_path):
    run(member_files(), [], tmp_path)
    first = {f.name: f.read_text() for f in (tmp_path / "targets").glob("*.csv")}

    run(member_files(), [], tmp_path)
    second = {f.name: f.read_text() for f in (tmp_path / "targets").glob("*.csv")}

    assert first == second


def test_replaying_an_old_file_does_not_undo_a_move(tmp_path):
    day1, day2 = member_files()
    run([day1, day2], [], tmp_path)

    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    shutil.copy(day1, replay_dir / day1.name)
    summary = run([replay_dir / day1.name], [], tmp_path)

    usa = {row.get("member_id") for row in read_csv(tmp_path / "targets" / "TABLE_USA.csv")}
    assert "223458" in usa
    assert summary.ignored_as_older >= 1


def test_redemption_status_update_and_orphans(summary_and_output):
    summary, out = summary_and_output

    txns = {row.get("txn_id"): row.get("status") for row in read_csv(out / "redemptions" / "redemptions_flat.csv")}
    orphans = [issue.member_id for issue in summary.issues if issue.rule == "ORPHAN_REDEMPTION"]

    assert txns.get("RX10092") == "COMPLETED"
    assert orphans == ["999999"]
