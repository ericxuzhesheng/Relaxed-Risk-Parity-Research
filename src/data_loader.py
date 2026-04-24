import os
import pandas as pd
import numpy as np
import tushare as ts
import time
from datetime import datetime, timedelta
from src.utils import resolve_path, get_config

# 精简后的核心资产映射表 (25个)
ASSET_MAP = {
    # --- 债券及衍生品 ---
    "0-5中高信用票": ("932339.CSI", "I"),
    "中证转债": ("000832.SH", "I"),
    "CFFEX2年期国债期货": ("TS.CFE", "F"),
    "CFFEX10年期国债期货": ("T.CFE", "F"),
    "CFFEX30年期国债期货": ("TL.CFE", "F"),
    "CBOT10年美债连续": ("TY00.CBT", "F"),
    
    # --- 宽基指数 ---
    "沪深300ETF": ("510300.SH", "E"),
    "中证1000ETF": ("512100.SH", "E"),
    "科创50ETF": ("588000.SH", "E"),
    "红利ETF": ("510880.SH", "E"),
    "上证指数ETF": ("510210.SH", "E"),
    "恒生ETF": ("159920.SZ", "E"),
    "恒生科技ETF": ("513180.SH", "E"),
    "纳指ETF": ("159941.SZ", "E"),
    "标普500ETF": ("513500.SH", "E"),
    "日经225ETF": ("513880.SH", "E"),
    
    # --- 核心外汇 ---
    "美元指数": ("USDX.FX", "X"),
    "离岸人民币": ("USDCNY.FX", "X"),
    "欧元兑美元": ("EURUSD.FX", "X"),
    "英镑兑美元": ("GBPUSD.FX", "X"),
    "美元兑日元": ("USDJPY.FX", "X"),
    
    # --- 核心商品 ---
    "黄金ETF": ("518880.SH", "E"),
    "有色ETF": ("159980.SZ", "E"),
    "WTI原油": ("CL.NYM", "F"),
    "豆粕连续": ("M.DCE", "F"),
}

def fetch_from_tushare(start_date="20180101", end_date=None):
    config = get_config()
    ts.set_token(config["tushare_token"])
    pro = ts.pro_api()
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    all_data = []
    print(f"Starting Precision Sync ({len(ASSET_MAP)} core assets)...")
    for name, (code, asset_type) in ASSET_MAP.items():
        print(f"  Syncing {name} ({code})...")
        try:
            df = None
            if asset_type == "E": df = pro.fund_daily(ts_code=code, start_date=start_date, end_date=end_date)
            elif asset_type == "I": df = pro.index_daily(ts_code=code, start_date=start_date, end_date=end_date)
            elif asset_type == "F": df = pro.fut_daily(ts_code=code, start_date=start_date, end_date=end_date)
            elif asset_type == "X": df = pro.fx_daily(ts_code=code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                date_col = 'trade_date' if 'trade_date' in df.columns else 'date'
                df = df[[date_col, 'close']]
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.set_index(date_col).sort_index()
                df.columns = [name]
                all_data.append(df)
            time.sleep(0.3)
        except Exception as e:
            print(f"  Skip {name}: {e}")
    if not all_data:
        raise ValueError("No data fetched.")
    final_df = pd.concat(all_data, axis=1)
    cache_path = resolve_path("data/processed/tushare_data.csv")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    final_df.to_csv(cache_path)
    return final_df

def load_data(source="tushare", force_update=False):
    if source == "tushare":
        cache_path = resolve_path("data/processed/tushare_data.csv")
        if force_update or not os.path.exists(cache_path):
            df = fetch_from_tushare()
        else:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    else:
        file_path = str(resolve_path("资产数据.xlsx"))
        df_raw = pd.read_excel(file_path, header=None)
        names = df_raw.iloc[3, 1:].tolist()
        df = df_raw.iloc[5:].copy()
        df.columns = ['date'] + [str(n).strip() for n in names]
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
    df = df.apply(pd.to_numeric, errors='coerce')
    df = df.ffill().bfill()
    df_returns = df.pct_change().dropna(how="all")
    def remove_outliers(series):
        m, s = series.mean(), series.std()
        return series.mask((series - m).abs() > 3 * s)
    return df_returns.apply(remove_outliers).dropna(how="all")

def update_data_from_wind(file_path=None):
    print("Wind update placeholder")
    return None
