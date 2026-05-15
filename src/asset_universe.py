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
    AssetMapping("中证转债",      "可转债ETF",   "511380.SH", "convertible bond",
                 "Convertible-bond ETF providing equity-linked credit exposure with downside protection."),
    AssetMapping("国债ETF",       "国债ETF",     "511010.SH", "government bond",
                 "Government bond ETF for duration exposure; the duration anchor of the risk parity portfolio."),
    AssetMapping("信用债ETF",     "信用债ETF",   "511030.SH", "credit bond",
                 "Credit spread bond ETF capturing yield pickup over government bonds."),
    AssetMapping("日利ETF",       "日利ETF",     "511880.SH", "money market",
                 "Money market ETF providing the ultra-short duration cash management layer."),
    # ── A 股宽基 ──────────────────────────────────────────────────────────────
    AssetMapping("沪深300ETF",    "沪深300ETF",  "510300.SH", "china equity",
                 "Broad China large-cap equity ETF tracking the CSI 300 index."),
    AssetMapping("中证500ETF",    "中证500ETF",  "510500.SH", "china equity",
                 "Mid-cap China equity ETF tracking the CSI 500 index."),
    AssetMapping("中证1000ETF",   "中证1000ETF", "512100.SH", "china equity",
                 "Small-cap China equity ETF tracking the CSI 1000 index."),
    AssetMapping("科创50ETF",     "科创50ETF",   "588000.SH", "china equity",
                 "STAR 50 ETF providing dedicated exposure to mainland-listed innovation companies."),
    AssetMapping("红利ETF",       "红利ETF",     "510880.SH", "china equity dividend",
                 "Dividend equity ETF tilting toward high-yield, defensive A-share names."),
    # ── 中国科技与增长 ─────────────────────────────────────────────────────────
    AssetMapping("半导体ETF",     "半导体ETF",   "512480.SH", "china tech equity",
                 "Semiconductor ETF capturing core hardware factor across the China chip value chain."),
    AssetMapping("人工智能ETF",   "人工智能ETF", "159819.SZ", "china tech equity",
                 "Artificial intelligence ETF covering software, algorithms, and applied AI services."),
    AssetMapping("机器人ETF",     "机器人ETF",   "562500.SH", "china advanced manufacturing",
                 "Robotics and intelligent manufacturing ETF capturing industrial automation growth."),
    AssetMapping("新能源ETF",     "新能源ETF",   "516160.SH", "china new energy",
                 "Broad new-energy ETF covering electric vehicles, energy storage, and solar."),
    AssetMapping("消费电子ETF",   "消费电子ETF", "159839.SZ", "china tech equity",
                 "Consumer electronics ETF covering smartphone components, displays, and wearables."),
    AssetMapping("通信ETF",       "通信ETF",     "159695.SZ", "china tech equity",
                 "Telecom and 5G ETF covering network equipment, base stations, and fiber optics."),
    AssetMapping("云计算ETF",     "云计算ETF",   "516980.SH", "china tech equity",
                 "Cloud computing ETF covering SaaS, cloud infrastructure, and digital services."),
    # ── 中国行业与消费 ────────────────────────────────────────────────────────
    AssetMapping("证券ETF",       "证券ETF",     "512880.SH", "china finance",
                 "China brokerage and securities sector ETF for market-cyclical beta."),
    AssetMapping("军工ETF",       "军工ETF",     "512660.SH", "china defense",
                 "China defense and military industry ETF for aerospace, shipbuilding, and high-end equipment."),
    AssetMapping("消费ETF",       "消费ETF",     "159928.SZ", "china consumer",
                 "CSI Main Consumer ETF covering food, beverages, and household goods — domestic demand factor."),
    # ── 港股 ──────────────────────────────────────────────────────────────────
    AssetMapping("恒生ETF",       "恒生ETF",     "159920.SZ", "hong kong equity",
                 "Hang Seng Index ETF providing broad Hong Kong equity exposure."),
    AssetMapping("恒生科技ETF",   "恒生科技ETF", "513180.SH", "hong kong equity",
                 "Hang Seng TECH ETF covering Hong Kong-listed China internet and tech leaders."),
    # ── 全球股票 ──────────────────────────────────────────────────────────────
    AssetMapping("纳指ETF",       "纳指ETF",     "159941.SZ", "global equity",
                 "Nasdaq-100 ETF providing US growth and technology exposure."),
    AssetMapping("标普500ETF",    "标普500ETF",  "513500.SH", "global equity",
                 "S&P 500 ETF providing US large-cap blue-chip exposure."),
    AssetMapping("日经225ETF",    "日经225ETF",  "513880.SH", "global equity",
                 "Nikkei 225 ETF providing Japanese equity exposure."),
    AssetMapping("欧洲ETF",       "欧洲ETF",     "513030.SH", "global equity",
                 "S&P Europe 350 ETF providing developed European market exposure."),
    # ── 大宗商品 ──────────────────────────────────────────────────────────────
    AssetMapping("黄金ETF",       "黄金ETF",     "518880.SH", "commodity",
                 "Gold ETF providing precious-metal inflation hedge and tail-risk diversification."),
    AssetMapping("有色ETF",       "有色ETF",     "159980.SZ", "commodity equity",
                 "Non-ferrous metals ETF capturing industrial commodity demand."),
    AssetMapping("豆粕连续",      "豆粕ETF",     "159985.SZ", "commodity",
                 "Soybean meal ETF providing agricultural commodity exposure."),
    AssetMapping("煤炭ETF",       "煤炭ETF",     "515220.SH", "commodity",
                 "Coal ETF capturing traditional energy factor with independent supply dynamics."),
    AssetMapping("原油ETF",       "原油ETF",     "162411.SZ", "commodity",
                 "Global oil and gas ETF tracking the S&P energy index for crude oil price exposure."),
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
