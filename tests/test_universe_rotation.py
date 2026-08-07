from src.asset_universe import CANDIDATE_UNIVERSE, ETF_UNIVERSE


ACTIVE_IN = {"563300.SH", "159981.SZ", "511260.SH"}
ACTIVE_OUT = {"562500.SH", "513310.SH", "516980.SH"}
REMAINING_CANDIDATES = {"511090.SH", "520830.SH", "520870.SH"}


def test_rotated_active_universe_has_exactly_30_disjoint_etfs():
    active = {item.ticker for item in ETF_UNIVERSE}
    candidates = {item.ticker for item in CANDIDATE_UNIVERSE}

    assert len(ETF_UNIVERSE) == 30
    assert len(CANDIDATE_UNIVERSE) == 6
    assert len(active | candidates) == 36
    assert active.isdisjoint(candidates)


def test_requested_rotation_moves_out_etfs_to_candidates():
    active = {item.ticker for item in ETF_UNIVERSE}
    candidates = {item.ticker for item in CANDIDATE_UNIVERSE}

    assert ACTIVE_IN <= active
    assert ACTIVE_OUT.isdisjoint(active)
    assert ACTIVE_OUT <= candidates
    assert REMAINING_CANDIDATES <= candidates


def test_nonferrous_futures_etf_is_classified_as_commodity():
    mapping = {item.ticker: item for item in ETF_UNIVERSE}

    assert mapping["159980.SZ"].asset_class == "commodity"

