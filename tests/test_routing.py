from datetime import date, datetime

from conftest import make_member
from skypoints.routing import CurrentLocation, latest_record_wins, plan_country_routing


def test_last_line_wins_inside_the_same_file():
    first = make_member(line_number=2, tier_code="SLV")
    second = make_member(line_number=3, tier_code="GLD")

    winners, superseded = latest_record_wins([second, first])  # input order must not matter

    assert [w.tier_code for w in winners] == ["GLD"]
    assert superseded == [first]


def test_newer_business_date_wins_over_line_number():
    newer = make_member(business_date=date(2024, 1, 16), line_number=2, country="IND")
    older = make_member(business_date=date(2024, 1, 15), line_number=99, country="USA")

    winners, _ = latest_record_wins([newer, older])

    assert winners[0].country_code == "IND"


def test_later_extract_on_same_day_wins():
    morning = make_member(extract_ts=datetime(2024, 1, 15, 1, 0), country="USA")
    evening = make_member(extract_ts=datetime(2024, 1, 15, 22, 0), country="CAN")

    winners, _ = latest_record_wins([evening, morning])

    assert winners[0].country_code == "CAN"


def test_new_member_is_upserted_into_its_country_table():
    plan = plan_country_routing([make_member(country="IND")])

    assert [m.member_id for m in plan.upserts["TABLE_INDIA"]] == ["223457"]
    assert dict(plan.deletes) == {}


def test_member_who_moved_country_is_deleted_from_old_table():
    current = {"223457": CurrentLocation("IND", date(2024, 1, 15))}
    moved = make_member(business_date=date(2024, 1, 16), country="USA")

    plan = plan_country_routing([moved], current)

    assert [m.member_id for m in plan.upserts["TABLE_USA"]] == ["223457"]
    assert plan.deletes["TABLE_INDIA"] == ["223457"]
    assert plan.moves == [("223457", "IND", "USA")]


def test_late_arriving_older_record_does_not_overwrite_newer_data():
    current = {"223457": CurrentLocation("USA", date(2024, 1, 16))}
    late = make_member(business_date=date(2024, 1, 15), country="IND")

    plan = plan_country_routing([late], current)

    assert plan.ignored_as_older == [late]
    assert dict(plan.upserts) == {}
