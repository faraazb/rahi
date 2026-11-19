"""Station label matching: exact first, then reported loose matches."""

import pytest

from mumbailocal.stations import StationTable


@pytest.fixture(scope="module")
def wr():
    return StationTable("WR")


@pytest.mark.parametrize("label,code,how", [
    ("CHURCHGATE", "CCG", "exact"),
    ("M'BAI CENTRAL (L)", "BCL", "exact"),
    ("CHURCHGATE D", "CCG", "qualifier"),       # departure marker column
    ("M'BAI CENTRAL A", "BCL", "qualifier"),    # arrival marker
    ("Grant Road C/S", "GTR", "qualifier"),     # car-shed note
    ("Charni Road EX VR", "CYR", "qualifier"),  # origin note
    ("CHURCHGAT", "CCG", "prefix"),             # truncated
    ("M'BAI CENTR", "BCL", "prefix"),
    ("Ville Parle", "VLP", "typo"),             # one letter off
])
def test_match(wr, label, code, how):
    st, kind = wr.match(label)
    assert (st.code, kind) == (code, how)


@pytest.mark.parametrize("label", ["D", "A", "NOT ON SUNDAY", "STATIONS", "Passing (Will not halt at BVI)", ""])
def test_no_false_matches(wr, label):
    assert wr.match(label) == (None, "")


def test_loose_matching_never_uses_bare_codes(wr):
    # "BA D" must not become Bandra through the code "BA" plus a stripped marker.
    assert wr.match("BA D")[0] is None
