import json
from datetime import date

from skypoints.redemptions import (
    flatten_redemptions,
    latest_transaction_state,
    load_feed_objects,
    summarise_by_member,
)

SAMPLE = {
    "member_id": "223457",
    "feed_date": "20240115",
    "redemptions": [
        {
            "txn_id": "RX10091",
            "txn_date": "20240110",
            "partner": "AeroLink",
            "miles_redeemed": 12000,
            "status": "COMPLETED",
        },
        {
            "txn_id": "RX10092",
            "txn_date": "20240113",
            "partner": "SkyPoints",
            "miles_redeemed": 5000,
            "status": "PENDING",
        },
    ],
}


def txn(**overrides):
    """A one-transaction feed object; overrides change only the fields a test cares about."""
    base = {
        "txn_id": "RX1",
        "txn_date": "20240110",
        "partner": "AeroLink",
        "miles_redeemed": 100,
        "status": "COMPLETED",
    }
    return {"member_id": "1", "feed_date": "20240115", "redemptions": [{**base, **overrides}]}


def test_flattens_one_row_per_transaction_with_parent_fields():
    rows, issues = flatten_redemptions([SAMPLE], "f.json")

    assert issues == []
    assert [(r.txn_id, r.member_id, r.feed_date) for r in rows] == [
        ("RX10091", "223457", date(2024, 1, 15)),
        ("RX10092", "223457", date(2024, 1, 15)),
    ]


def test_reads_single_object_array_and_ndjson():
    single = json.dumps(SAMPLE)
    array = json.dumps([SAMPLE, SAMPLE])
    ndjson = single + "\n" + single + "\n"

    assert len(list(load_feed_objects(single))) == 1
    assert len(list(load_feed_objects(array))) == 2
    assert len(list(load_feed_objects(ndjson))) == 2


def test_invalid_transactions_are_rejected_with_a_reason():
    feeds = [
        txn(miles_redeemed=-50),
        txn(miles_redeemed="5000"),
        txn(status="LOST"),
        txn(txn_date="20240120"),
        txn(txn_date="2024-01-10"),
        txn(txn_id=None),
    ]

    rows, issues = flatten_redemptions(feeds, "f.json")

    assert rows == []
    assert [i.rule for i in issues] == [
        "INVALID_MILES",
        "INVALID_MILES",
        "INVALID_STATUS",
        "TXN_AFTER_FEED_DATE",
        "INVALID_DATE",
        "TXN_ID_MISSING",
    ]


def test_member_without_redemptions_array_produces_no_rows():
    rows, issues = flatten_redemptions([{"member_id": "1", "feed_date": "20240115"}], "f.json")

    assert (rows, issues) == ([], [])


def test_status_update_in_later_feed_replaces_earlier_version():
    day1, _ = flatten_redemptions([txn(status="PENDING")], "d1.json")
    day2_feed = txn(status="COMPLETED")
    day2_feed["feed_date"] = "20240116"
    day2, _ = flatten_redemptions([day2_feed], "d2.json")

    current = latest_transaction_state(day1 + day2)

    assert [(t.txn_id, t.status) for t in current] == [("RX1", "COMPLETED")]


def test_summary_splits_completed_and_pending_and_flags_orphans():
    rows, _ = flatten_redemptions([SAMPLE], "f.json")

    summaries = summarise_by_member(rows, known_member_ids=set())

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.completed_miles == 12000
    assert summary.pending_miles == 5000
    assert summary.last_redemption_date == date(2024, 1, 10)
    assert summary.is_known_member is False
