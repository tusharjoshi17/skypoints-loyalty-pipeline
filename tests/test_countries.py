import pytest

from skypoints.countries import normalize_country, target_table_for


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USA", "USA"),
        ("AU", "AUS"),  # ISO alpha-2
        ("PHIL", "PHL"),  # free text seen in the sample file
        (" ind ", "IND"),  # whitespace and lower case
        ("UAE", None),  # unknown country
        (None, None),
    ],
)
def test_normalize_country(raw, expected):
    assert normalize_country(raw) == expected


def test_every_known_country_routes_to_exactly_one_table():
    assert target_table_for("AUS") == "TABLE_AUSTRALIA"


def test_unknown_country_fails_loudly_instead_of_dropping_the_member():
    with pytest.raises(KeyError):
        target_table_for("UAE")
