"""compose_actual_data_hash の contract test。

cloud-run/tests/test_team_budget_hash.py と同じ test を持つことで
cross-side consistency を機械的に保証する (Codex 指摘 a/g 対応)。

両側の hash 値が一致しなくなる変更は contract 違反として両方の test が落ちる。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.team_budget_hash import compose_actual_data_hash


# ---- contract cases (cloud-run/tests/test_team_budget_hash.py と同期) ----
CONTRACT_CASES = [
    ("", None, "v1",
     "02b585467e2cd3ff561572767e29a165aa4a04df3a38a6d13dd83d9e004067d8"),
    ("abc123", None, "v1",
     "0c94a188ed2313d0f364277168981a073d6aef39ca9e32cc19d8fd7e7a556c16"),
    ("abc123", Decimal("1000"), "v1",
     "e3a72770048c425ee11ddcc27653181282e533f47d3f69291f63b45a5b624d24"),
    ("abc123", Decimal("1500.50"), "v1",
     "c2edc6ba4a279be349af535ebd0a05e250ed3c4429f3f74fdd862e5b10213b31"),
    ("abc123", Decimal("1000"), "v2",
     "d62d572f045d57611b26b8585b44d732f9ab050e7d1b28811b451fffc67065df"),
    ("abc123", Decimal("0"), "v1",
     "d2532c6be36e801b6379ff719c35fc8b4a675dd6a38bd825463a8eeb9e36b2b0"),
]


class TestComposeActualDataHashContract:
    @pytest.mark.parametrize("bq_hash,budget,prompt_version,expected", CONTRACT_CASES)
    def test_contract_cases_match_expected(self, bq_hash, budget, prompt_version, expected):
        assert compose_actual_data_hash(bq_hash, budget, prompt_version) == expected


class TestComposeActualDataHashNormalization:
    """Decimal/float/int の同一性正規化 (Codex 指摘 j)"""

    def test_int_decimal_float_same_hash_for_integer_value(self):
        h_int = compose_actual_data_hash("abc123", 1000, "v1")
        h_dec = compose_actual_data_hash("abc123", Decimal("1000"), "v1")
        h_float = compose_actual_data_hash("abc123", 1000.0, "v1")
        assert h_int == h_dec == h_float

    def test_trailing_zero_decimal_same_as_no_trailing(self):
        h_no = compose_actual_data_hash("abc123", Decimal("1000"), "v1")
        h_one = compose_actual_data_hash("abc123", Decimal("1000.0"), "v1")
        h_two = compose_actual_data_hash("abc123", Decimal("1000.00"), "v1")
        assert h_no == h_one == h_two

    def test_float_fractional_same_as_decimal(self):
        h_float = compose_actual_data_hash("abc123", 1500.5, "v1")
        h_dec = compose_actual_data_hash("abc123", Decimal("1500.50"), "v1")
        assert h_float == h_dec

    def test_none_distinct_from_zero(self):
        h_none = compose_actual_data_hash("abc123", None, "v1")
        h_zero = compose_actual_data_hash("abc123", Decimal("0"), "v1")
        assert h_none != h_zero

    def test_empty_bq_hash_distinct_from_nonempty(self):
        h_empty = compose_actual_data_hash("", Decimal("1000"), "v1")
        h_full = compose_actual_data_hash("abc123", Decimal("1000"), "v1")
        assert h_empty != h_full

    def test_returns_64_char_hex(self):
        h = compose_actual_data_hash("abc123", Decimal("1000"), "v1")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
