import os
import pandas as pd
import numpy as np
import glob
from datetime import datetime, timedelta
from src.utils import resolve_path

try:
    from WindPy import w
    WIND_AVAILABLE = True
except ImportError:
    WIND_AVAILABLE = False

def update_data_from_wind(file_path: str = None) -> str:
    if not WIND_AVAILABLE:
        print("Warning: WindPy not available. Skipping update.")
        return None
    
    if file_path is None:
        file_path = str(resolve_path("资产数据.xlsx"))
        if not os.path.exists(file_path):
            files = glob.glob(str(resolve_path("资产数据*.xlsx")))
            if files:
                files.sort(reverse=True)
                file_path = files[0]
            else:
                return None

    if not w.isconnected():
        w.start()
    
    df = pd.read_excel(file_path, header=None)
    TICKER_ROW_INDEX = 4
    DATA_START_INDEX = 5
    DATE_COL_INDEX = 0
    
    raw_tickers = df.iloc[TICKER_ROW_INDEX, 1:].tolist()
    valid_tickers = [t for t in raw_tickers if isinstance(t, str) and t.strip()]
    ticker_col_map = {t: i + 1 for i, t in enumerate(raw_tickers) if t in valid_tickers}
    
    last_date = pd.to_datetime(df.iloc[-1, DATE_COL_INDEX])
    start_date = last_date + timedelta(days=1)
    end_date = datetime.now()
    
    if start_date.date() > end_date.date():
        return file_path

    wind_data = w.wsd(",".join(valid_tickers), "close", start_date, end_date, "")
    if wind_data.ErrorCode != 0 or not wind_data.Data:
        return file_path

    new_dates = [pd.to_datetime(d) for d in wind_data.Times]
    new_rows = []
    for i in range(len(new_dates)):
        row = [None] * df.shape[1]
        row[DATE_COL_INDEX] = new_dates[i]
        for idx, code in enumerate(wind_data.Codes):
            col_idx = ticker_col_map.get(code)
            if col_idx is not None:
                row[col_idx] = wind_data.Data[idx][i]
        new_rows.append(row)
        
    updated_df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    updated_df.to_excel(file_path, index=False, header=False)
    return file_path

def load_data(file_path: str) -> pd.DataFrame:
    """加载数据并预处理为收益率格式"""
    file_path = str(resolve_path(file_path))
    if file_path.endswith('.xlsx'):
        # 针对本项目Excel结构的特殊处理
        df_raw = pd.read_excel(file_path, header=None)
        names = df_raw.iloc[3, 1:].tolist()
        # 创建列名映射
        col_names = ['date'] + [str(n).strip() for n in names]
        df = df_raw.iloc[5:].copy()
        df.columns = col_names
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
    else:
        df = pd.read_csv(file_path, parse_dates=["date"], index_col="date")
    
    df.index = pd.to_datetime(df.index)
    df = df.sort_index(ascending=True)
    
    # 转换为收益率
    if np.abs(df).max().max() > 1:
        df_returns = df.pct_change().dropna(how="all")
    else:
        df_returns = df.copy()
    
    # 3 sigma 异常值处理
    def remove_outliers(series):
        m, s = series.mean(), series.std()
        return series.mask((series - m).abs() > 3 * s)

    df_returns = df_returns.apply(remove_outliers)
    return df_returns.dropna(how="all")
