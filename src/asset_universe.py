from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class AssetMapping:
    old_name: str
    new_name: str
    ticker: str
    asset_class: str
    reason: str
    data_source_field: str = "adj_close"


ETF_UNIVERSE: tuple[AssetMapping, ...] = (
    # ── 债券类 ────────────────────────────────────────────────────────────────
    AssetMapping("0-5中高信用票", "短融ETF",     "511360.SH", "short-duration credit",
                 "Replace non-ETF credit index with a tradable short-duration bond ETF."),
    AssetMapping("中证转债",      "可转债ETF",   "511380.SH", "convertible bond",
                 "Replace convertible-bond index with a tradable convertible-bond ETF."),
    AssetMapping("国债ETF",       "国债ETF",     "511010.SH", "government bond",
                 "Add government bond ETF for duration exposure; critical for risk parity bond anchor."),
    AssetMapping("信用债ETF",     "信用债ETF",   "511030.SH", "credit bond",
                 "Add credit spread bond ETF for yield pickup over government bonds."),
    AssetMapping("银华日利ETF",   "银华日利ETF", "511880.SH", "money market",
                 "Add money market ETF for ultra-short duration cash management layer."),
    # ── A 股宽基 ──────────────────────────────────────────────────────────────
    AssetMapping("沪深300ETF",    "沪深300ETF",  "510300.SH", "china equity",
                 "Existing tradable broad China equity ETF."),
    AssetMapping("中证500ETF",    "中证500ETF",  "510500.SH", "china equity",
                 "Add mid-cap China equity exposure."),
    AssetMapping("中证1000ETF",   "中证1000ETF", "512100.SH", "china equity",
                 "Existing tradable small-cap China equity ETF."),
    AssetMapping("科创50ETF",     "科创50ETF",   "588000.SH", "china equity",
                 "Existing tradable STAR 50 ETF."),
    AssetMapping("红利ETF",       "红利ETF",     "510880.SH", "china equity dividend",
                 "Existing tradable dividend equity ETF."),
    # ── 中国科技（弹性） ──────────────────────────────────────────────────────
    AssetMapping("半导体ETF",     "半导体ETF",   "512480.SH", "china tech equity",
                 "Add semiconductor ETF for China tech elasticity."),
    AssetMapping("芯片ETF",       "芯片ETF",     "159995.SZ", "china tech equity",
                 "Add chip ETF for additional China semiconductor exposure."),
    AssetMapping("机器人ETF",     "机器人ETF",   "562500.SH", "china advanced manufacturing",
                 "China robotics and intelligent manufacturing ETF capturing automation, industrial robots, and smart equipment growth factor exposure."),
    AssetMapping("人工智能ETF",   "人工智能ETF", "159819.SZ", "china tech equity",
                 "Add AI/new-economy ETF for China tech upside elasticity."),
    AssetMapping("卫星ETF",       "卫星ETF",     "159206.SZ", "china tech equity",
                 "Add satellite/space industry ETF for aerospace technology factor exposure."),
    # ── 中国新能源 ────────────────────────────────────────────────────────────
    AssetMapping("光伏ETF",       "光伏ETF",     "515790.SH", "china new energy",
                 "Add solar/PV ETF for clean energy factor."),
    AssetMapping("新能源ETF",     "新能源ETF",   "516160.SH", "china new energy",
                 "Add broad new energy ETF (NEV+storage+solar)."),
    # ── 中国行业 ──────────────────────────────────────────────────────────────
    AssetMapping("证券ETF",       "证券ETF",     "512880.SH", "china finance",
                 "Add China brokerage/securities sector for market-cyclical beta."),
    # ── 港股 ──────────────────────────────────────────────────────────────────
    AssetMapping("恒生ETF",       "恒生ETF",     "159920.SZ", "hong kong equity",
                 "Existing tradable Hong Kong equity ETF."),
    AssetMapping("创新药ETF",     "创新药ETF",   "516080.SH", "china pharma",
                 "China innovative pharmaceuticals ETF providing healthcare growth and defensive diversification across biotech, oncology, and novel therapy pipelines."),
    # ── 全球股票 ──────────────────────────────────────────────────────────────
    AssetMapping("纳指ETF",       "纳指ETF",     "159941.SZ", "global equity",
                 "Existing tradable Nasdaq ETF."),
    AssetMapping("军工ETF",       "军工ETF",     "512660.SH", "china defense",
                 "China defense and military industry ETF providing cyclical exposure to aerospace, shipbuilding, and high-end equipment manufacturing."),
    AssetMapping("标普500ETF",    "标普500ETF",  "513500.SH", "global equity",
                 "Existing tradable S&P 500 ETF."),
    AssetMapping("日经225ETF",    "日经225ETF",  "513880.SH", "global equity",
                 "Existing tradable Nikkei 225 ETF."),
    AssetMapping("道琼斯ETF",     "道琼斯ETF",   "513400.SH", "global equity",
                 "Replace German DAX with Dow Jones Industrial ETF for US large-cap blue-chip diversification."),
    # ── 大宗商品 ──────────────────────────────────────────────────────────────
    AssetMapping("黄金ETF",       "黄金ETF",     "518880.SH", "commodity",
                 "Existing tradable gold ETF."),
    AssetMapping("有色ETF",       "有色ETF",     "159980.SZ", "commodity equity",
                 "Existing tradable non-ferrous metals ETF."),
    AssetMapping("豆粕连续",      "豆粕ETF",     "159985.SZ", "commodity",
                 "Replace commodity futures series with a tradable soybean meal ETF."),
    AssetMapping("油气ETF",       "油气ETF",     "513350.SH", "commodity",
                 "Add S&P global oil & gas ETF for energy commodity exposure."),
    AssetMapping("煤炭ETF",       "煤炭ETF",     "515220.SH", "commodity",
                 "Add coal ETF for traditional energy factor with independent supply dynamics."),
)


def asset_mapping_frame() -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in ETF_UNIVERSE])


def ticker_to_name() -> dict[str, str]:
    return {item.ticker: item.new_name for item in ETF_UNIVERSE}


def old_to_new_name() -> dict[str, str]:
    return {item.old_name: item.new_name for item in ETF_UNIVERSE}


def etf_tickers() -> list[str]:
    return [item.ticker for item in ETF_UNIVERSE]


def etf_names() -> list[str]:
    return [item.new_name for item in ETF_UNIVERSE]
