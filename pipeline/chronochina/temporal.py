from __future__ import annotations

import re


INTEGER_YEAR = re.compile(r"^[+-]?\d+$")


def parse_year(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value or not INTEGER_YEAR.fullmatch(value):
        return None
    return int(value)


def valid_for(valid_from: int | None, valid_to: int | None, year: int) -> bool:
    if valid_from is None or valid_to is None or valid_from > valid_to:
        return False
    return valid_from <= year <= valid_to
