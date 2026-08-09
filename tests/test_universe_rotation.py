from src.asset_universe import CANDIDATE_UNIVERSE, ETF_UNIVERSE
from src.data_loader import load_data
from src.investable import investable_columns


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


def test_mislabeled_516980_candidate_uses_official_asset_identity():
    mapping = {item.ticker: item for item in CANDIDATE_UNIVERSE}

    assert mapping["516980.SH"].new_name == "证券公司先锋策略ETF"
    assert mapping["516980.SH"].asset_class == "china finance"


def test_point_in_time_universe_at_2018_start_and_late_entry() -> None:
    returns = load_data(source="tushare", force_update=False)
    start_window = returns[returns.index < "2018-01-02"].iloc[-240:]
    assert len(investable_columns(start_window, min_observations=60)) == 18

    csi2000 = next(item.new_name for item in ETF_UNIVERSE if item.ticker == "563300.SH")
    before_entry = returns[returns.index < "2023-12-01"].iloc[-240:]
    after_entry = returns[returns.index < "2024-01-31"].iloc[-240:]
    assert csi2000 not in investable_columns(before_entry, min_observations=60)
    assert csi2000 in investable_columns(after_entry, min_observations=60)
