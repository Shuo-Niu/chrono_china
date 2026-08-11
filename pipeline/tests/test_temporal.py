import pytest

from chronochina.temporal import parse_year, valid_for


@pytest.mark.parametrize(
    ("year", "expected"),
    [(100, True), (150, True), (200, True), (99, False), (201, False)],
)
def test_valid_for_uses_closed_interval(year: int, expected: bool) -> None:
    assert valid_for(100, 200, year) is expected


def test_valid_for_supports_bce_and_ce() -> None:
    assert valid_for(-221, 9, -221)
    assert valid_for(-221, 9, 0)
    assert valid_for(-221, 9, 9)
    assert not valid_for(-221, 9, -222)


@pytest.mark.parametrize("bounds", [(None, 10), (1, None), (20, 10)])
def test_invalid_or_missing_bounds_are_not_published(bounds: tuple[int | None, int | None]) -> None:
    assert not valid_for(*bounds, year=5)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("-221", -221), ("0", 0), ("1911", 1911), ("", None), ("1.5", None)],
)
def test_parse_year_does_not_guess_date_encoding(raw: str, expected: int | None) -> None:
    assert parse_year(raw) == expected
