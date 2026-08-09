from src.utils import infer_asset_class


def test_active_universe_classification_uses_declared_categories() -> None:
    assert infer_asset_class("日利ETF") == "cash"
    assert infer_asset_class("10年国债ETF") == "bond"
    assert infer_asset_class("信用债ETF") == "bond"
    assert infer_asset_class("能源化工期货ETF") == "commodity_gold"
    assert infer_asset_class("有色金属期货ETF") == "commodity_gold"
    assert infer_asset_class("红利ETF") == "defensive"
    assert infer_asset_class("沪深300ETF") == "equity"
