"""
资产配置月度更新脚本
整合了Wind数据获取和风险平价策略分析功能

功能：
1. 从Wind API获取最新资产价格数据并更新Excel文件
2. 执行风险平价策略回测分析
3. 生成绩效报告和可视化图表

使用方式：
    python 资产配置月度更新.py --update-wind --run-backtest
"""

import numpy as np
import pandas as pd
import akshare as ak
from typing import Tuple, List
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.dates as mdates
import warnings
from pathlib import Path
import argparse
import os
import sys
from datetime import datetime, timedelta

# 可选的Wind API导入
try:
    from WindPy import w
    WIND_AVAILABLE = True
except ImportError:
    WIND_AVAILABLE = False
    print("Warning: WindPy not available. Wind data update功能将被禁用。")

warnings.filterwarnings("ignore")

# Matplotlib配置（全局设置一次）
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE_DIR = Path(__file__).resolve().parent


def _resolve_path(path_like):
    if path_like is None:
        return None
    p = Path(path_like)
    return p if p.is_absolute() else (BASE_DIR / p)


# ==================== Wind数据更新模块 ====================
def update_data_from_wind(file_dir: str = None, base_filename: str = None) -> str:
    """
    从Wind API获取最新资产数据并更新Excel文件
    
    Args:
        file_dir: 文件目录，默认为脚本所在目录
        base_filename: 基础文件名，用于查找最新文件
        
    Returns:
        str: 更新后的文件路径
    """
    if not WIND_AVAILABLE:
        print("Error: WindPy not available. 无法执行Wind数据更新。")
        return None
    
    if file_dir is None:
        file_dir = str(BASE_DIR)
    
    # 查找最新的资产数据文件
    if base_filename is None:
        pattern = os.path.join(file_dir, "资产数据*.xlsx")
        files = glob.glob(pattern)
        if not files:
            print(f"Error: No asset data files found in {file_dir}")
            return None
        # 按文件名排序，取最新的
        files.sort(reverse=True)
        file_path = files[0]
    else:
        file_path = os.path.join(file_dir, base_filename)
    
    print(f"[{datetime.now()}] Starting asset data update process...")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return None

    # 连接Wind
    print("Connecting to Wind API...")
    try:
        if not w.isconnected():
            res = w.start()
            if res.ErrorCode != 0:
                print(f"Failed to connect to Wind. ErrorCode: {res.ErrorCode}")
                return None
        print("Wind connected successfully.")
    except Exception as e:
        print(f"Exception while connecting to Wind: {e}")
        print("Please ensure Wind Terminal is running and WindPy is installed.")
        return None

    # 读取Excel文件
    print(f"Reading file: {file_path}")
    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return None

    # 提取tickers和日期信息
    TICKER_ROW_INDEX = 4
    DATA_START_INDEX = 5
    DATE_COL_INDEX = 0
    
    raw_tickers = df.iloc[TICKER_ROW_INDEX, 1:].tolist()
    
    ticker_col_map = {}
    valid_tickers = []
    
    for idx, ticker in enumerate(raw_tickers):
        if isinstance(ticker, str) and ticker.strip():
            ticker_col_map[ticker] = idx + 1
            valid_tickers.append(ticker)
            
    print(f"Found {len(valid_tickers)} valid tickers")
    
    # 获取最后日期
    last_date_val = df.iloc[-1, DATE_COL_INDEX]
    try:
        last_date = pd.to_datetime(last_date_val)
        print(f"Last data date in file: {last_date.date()}")
    except Exception as e:
        print(f"Error parsing last date '{last_date_val}': {e}")
        return None
        
    # 确定更新范围
    start_date = last_date + timedelta(days=1)
    end_date = datetime.now()
    
    if start_date.date() > end_date.date():
        print("Data is already up to date.")
        return file_path

    print(f"Fetching data from {start_date.date()} to {end_date.date()}...")
    
    # 从Wind获取数据
    codes_str = ",".join(valid_tickers)
    wind_data = w.wsd(codes_str, "close", start_date, end_date, "")
    
    if wind_data.ErrorCode != 0:
        print(f"Wind Data Fetch Error: {wind_data.ErrorCode}")
        return None
        
    if not wind_data.Data:
        print("No data returned from Wind.")
        return None

    # 处理新数据
    new_dates = wind_data.Times
    if not new_dates:
        print("No new dates returned.")
        return None
        
    new_dates = [pd.to_datetime(d) if not isinstance(d, datetime) else d 
                 for d in new_dates]
    
    print(f"Retrieved {len(new_dates)} new records.")
    
    # 创建数据映射
    fetched_data_map = {}
    if len(wind_data.Codes) != len(wind_data.Data):
        if len(valid_tickers) == 1:
            fetched_data_map[wind_data.Codes[0]] = wind_data.Data
        else:
            print("Mismatch in Wind data codes and data length.")
    else:
        for idx, code in enumerate(wind_data.Codes):
            fetched_data_map[code] = wind_data.Data[idx]

    # 构建新行
    new_rows = []
    for i in range(len(new_dates)):
        row = [None] * df.shape[1]
        row[DATE_COL_INDEX] = new_dates[i]
        
        for ticker in valid_tickers:
            col_idx = ticker_col_map.get(ticker)
            if col_idx is not None and ticker in fetched_data_map:
                val = fetched_data_map[ticker][i]
                row[col_idx] = val
        
        new_rows.append(row)
        
    new_df = pd.DataFrame(new_rows, columns=df.columns)
    
    # 合并并保存
    df_updated = pd.concat([df, new_df], ignore_index=True)
    
    final_last_date = df_updated.iloc[-1, DATE_COL_INDEX]
    date_code = pd.to_datetime(final_last_date).strftime("%y%m%d")
    
    new_filename = f"资产数据{date_code}.xlsx"
    output_path = os.path.join(file_dir, new_filename)
    
    print(f"Saving updated file to: {output_path}")
    df_updated.to_excel(output_path, index=False, header=False, engine='openpyxl')
    print("Update completed successfully.")
    
    return output_path


# ==================== 数据加载和预处理 ====================
#自动寻找最新6位日期的资产数据文件
import glob
import re

# 匹配“资产数据”+6位数字日期+“.xlsx”
pattern = str(BASE_DIR / "资产数据*.xlsx")
files = glob.glob(pattern)
date_files = []
for f in files:
    m = re.search(r"资产数据(\d{6})\.xlsx$", Path(f).name)
    if m:
        date_files.append((m.group(1), f))
if not date_files:
    raise FileNotFoundError("未找到符合格式的资产数据文件（资产数据YYMMDD.xlsx）")
# 按日期倒序取最新
latest_date, latest_file = sorted(date_files, reverse=True)[0]
asset_df = pd.read_excel(_resolve_path(latest_file), skiprows=[4], header=3)
asset_df["日期"] = pd.to_datetime(asset_df["日期"])
asset_df = asset_df.rename(columns={"日期": "date"})

asset_df = asset_df.sort_values("date")
asset_df = asset_df[asset_df["date"] < pd.Timestamp("today").normalize()]
asset_df.to_csv(_resolve_path("资产数据.csv"), encoding="utf-8-sig", index=False)


def load_and_preprocess_data(file_path: str) -> pd.DataFrame:
    """加载并预处理数据，计算收益率，处理缺失值"""
    try:
        df = pd.read_csv(
            file_path, parse_dates=["date"], index_col="date"
        )  # 兼容小写date列名

    except Exception as e:
        # 兼容原代码的Date列名
        try:
            df = pd.read_csv(file_path, parse_dates=["Date"], index_col="Date")
        except:
            raise ValueError(f"数据加载失败：{e} | 请确保日期列名为date/Date")

    # 强制将索引转换为datetime类型（双重保险，避免parse_dates失效），并按时间正序排序
    df.index = pd.to_datetime(df.index)  # 双重保险，确保索引是datetime类型
    df = df.sort_index(ascending=True)  # 按日期从早到晚正序排序，为pct_change()铺路
    print("日期已转换为datetime类型并完成时间正序排序")

    # 区分价格数据（绝对值>1）和收益率数据（绝对值≤1）
    if np.abs(df).max().max() > 1:
        print("检测到价格数据，将按单个资产独立转换为日度收益率（先清理非交易日NaN）")
        # 初始化空DataFrame存储各资产处理后的收益率
        df_returns = pd.DataFrame(index=df.index)

        # 遍历每个资产（列），独立处理：删除该资产非交易日NaN -> 计算收益率
        for col in df.columns:
            # 步骤1：提取单个资产数据，删除该资产的非交易日NaN（仅保留自身有效交易日）
            single_asset = df[col].dropna()

            # 步骤2：对单个资产有效数据计算收益率，删除收益率计算产生的首行NaN
            single_asset_returns = single_asset.pct_change().dropna()

            # 步骤3：将该资产收益率存入结果DataFrame（自动对齐索引，缺失值保留为NaN）
            df_returns[col] = single_asset_returns

        # 步骤4：删除结果中全为NaN的行（仅保留至少有一个资产有效交易的日期）
        df_returns = df_returns.dropna(how="all")
    else:
        print("检测到收益率数据，直接使用（默认日度）")
        # 收益率数据也按单个资产清理非交易日NaN，再删除全NaN行
        df_returns = df.copy()
        for col in df_returns.columns:
            df_returns[col] = df_returns[col].dropna()
        df_returns = df_returns.dropna(how="all")

    # 新增：异常值处理（3σ原则）
    def remove_outliers(series):
        mean = series.mean()
        std = series.std()
        # 仅对非NaN数据进行异常值过滤，保留原索引
        return series[(series >= mean - 3 * std) & (series <= mean + 3 * std)]

    # 异常值处理后，删除全为NaN的行

    # 检查数据有效性（日度数据：1年需252个样本）

    return df_returns


def solve_standard_rp(Sigma: np.ndarray, n_assets: int) -> np.ndarray:
    """求解标准风险平价权重（Model 0）"""
    x0 = np.ones(n_assets) / n_assets
    zeta0 = Sigma @ x0
    sigma0 = np.sqrt(x0 @ Sigma @ x0)
    psi0 = sigma0 / np.sqrt(n_assets)  # 匹配约束x^TΣx ≤nψ²
    gamma0 = np.min(x0 * zeta0)  # 初始风险贡献下界

    v0_rp = np.concatenate((x0, zeta0, [psi0, gamma0]))

    # 目标函数（论文：min ψ-γ）
    def objective(v):
        psi = v[2 * n_assets]
        gamma = v[2 * n_assets + 1]
        return psi - gamma

    # 等式约束：ζ_i = (Σx)_i | sum(x)=1
    def eq_constraints(v):
        x = v[:n_assets]
        zeta = v[n_assets : 2 * n_assets]
        con1 = zeta - np.dot(Sigma, x)
        con2 = np.sum(x) - 1
        return np.concatenate([con1, [con2]])

    # 不等式约束：x_iζ_i ≥ γ² | x^TΣx ≤nψ²
    def ineq_constraints(v):
        x = v[:n_assets]
        zeta = v[n_assets : 2 * n_assets]
        psi = v[2 * n_assets]
        gamma = v[2 * n_assets + 1]

        con1 = x * zeta - gamma**2  # 风险贡献下界
        con2 = n_assets * psi**2 - np.dot(x, np.dot(Sigma, x))  # 组合风险上界
        return np.concatenate([con1, [con2]])

    # 优化边界
    bounds = (
        [CONFIG["asset_weight_bounds"] for _ in range(n_assets)]
        + [(0, None) for _ in range(n_assets)]
        + [(0, 10), (0, 10)]
    )

    # 优化求解
    try:
        result = minimize(
            objective,
            v0_rp,
            method="SLSQP",  # 替换为SLSQP（更快，适合高维）
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints},
            ],
            bounds=bounds,
            options={
                "ftol": CONFIG["optim_tol"],
                "maxiter": CONFIG["optim_maxiter"] * 2,  # 迭代次数翻倍
                "disp": False,  # 关闭冗余输出
            },
        )

    except Exception as e:
        print(f"标准RP优化异常：{e}，使用等权替代")
        return np.ones(n_assets) / n_assets

    # 收敛性检查
    if not result.success:
        print(f"标准RP优化未收敛：{result.message}，使用等权替代")
        return np.ones(n_assets) / n_assets

    return result.x[:n_assets]


def dynamic_bond_indices(df_period: pd.DataFrame) -> list:
    """动态识别当前窗口已上市的债券资产索引"""
    name_mask = df_period.columns.str.contains(
        "|".join(CONFIG["bond_keywords"]), na=False
    )

    # # 2. 特征规则：年化波动率≤阈值（排除低波动股票误判）

    # # 3. 数据完整性规则：排除当前窗口缺失率>5%的资产（未上市/数据异常）

    # 合并规则：满足名称/特征任一 + 数据有效
    bond_mask = name_mask
    return [i for i, is_bond in enumerate(bond_mask) if is_bond]


def _optimize_with_leverage(
    Sigma: np.ndarray, n_assets: int, bond_indices: list,
    mu: np.ndarray = None, Theta: np.ndarray = None, R_target: float = 0,
    is_relaxed: bool = False
) -> tuple:
    """通用杠杆优化函数（标准RP和宽松RP共用）"""
    l_max = CONFIG["bond_leverage_upper"]
    n_bonds = len(bond_indices)

    # 初始化
    x0 = np.ones(n_assets) / n_assets
    leverage_init = np.ones(n_assets)
    bond_leverage0 = leverage_init[bond_indices]
    leveraged_x0 = x0 * leverage_init
    zeta0 = Sigma @ leveraged_x0
    psi0 = np.sqrt(leveraged_x0 @ Sigma @ leveraged_x0) / np.sqrt(n_assets)
    gamma0 = np.min(x0 * zeta0)
    rho0 = 0.1 if is_relaxed else None

    v0 = np.concatenate((
        x0, zeta0, [psi0, gamma0],
        [rho0] if is_relaxed else [], bond_leverage0
    ))

    # 目标函数
    def objective(v):
        return v[2 * n_assets] - v[2 * n_assets + 1]  # min ψ - γ

    # 等式约束
    def eq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets:2*n_assets]
        idx = 2*n_assets + 3 if is_relaxed else 2*n_assets + 2
        bond_lev = v[idx:]
        leverage = np.ones(n_assets)
        leverage[bond_indices] = bond_lev
        con_zeta = zeta - Sigma @ (x * leverage)
        con_sum = np.sum(x) - 1
        return np.concatenate([con_zeta, [con_sum]])

    # 不等式约束
    def ineq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets:2*n_assets]
        psi, gamma = v[2*n_assets], v[2*n_assets + 1]
        idx = 2*n_assets + 3 if is_relaxed else 2*n_assets + 2
        bond_lev = v[idx:]

        leverage = np.ones(n_assets)
        leverage[bond_indices] = bond_lev
        leveraged_x = x * leverage

        con1 = x * zeta - gamma**2
        con2 = n_assets * psi**2 - leveraged_x @ Sigma @ leveraged_x
        con3, con4 = bond_lev - 1.0, l_max - bond_lev

        if is_relaxed:
            rho = v[2*n_assets + 2]
            con_rho = rho**2 - CONFIG["lambda_pen"] * (x @ Theta @ x)
            con2 = (n_assets * (psi**2 - rho**2) -
                    leveraged_x @ Sigma @ leveraged_x)
            con_ret = mu @ leveraged_x - R_target
            return np.concatenate(
                [con1, [con_rho, con2, con_ret], con3, con4]
            )
        return np.concatenate([con1, [con2], con3, con4])

    # 优化边界
    bounds = (
        [CONFIG["asset_weight_bounds"]] * n_assets +
        [(0, None)] * n_assets +
        [(0, 10)] * (3 if is_relaxed else 2) +
        [(1.0, l_max)] * n_bonds
    )

    # 求解
    try:
        result = minimize(
            objective, v0, method="SLSQP",
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints}
            ],
            bounds=bounds,
            options={
                "ftol": CONFIG["optim_tol"],
                "maxiter": CONFIG["optim_maxiter"] * 2,
                "disp": False
            }
        )

        if result.success:
            x_opt = result.x[:n_assets]
            leverage_opt = np.ones(n_assets)
            idx = 2*n_assets + 3 if is_relaxed else 2*n_assets + 2
            leverage_opt[bond_indices] = result.x[idx:]
            model_name = "Model C" if is_relaxed else "标准RP"
            lev_dict = dict(
                zip(bond_indices, leverage_opt[bond_indices].round(4))
            )
            print(f"{model_name}债券杠杆优化结果：{lev_dict}")
            return x_opt, leverage_opt
        else:
            model = 'Model C' if is_relaxed else '标准RP'
            print(f"{model}未收敛：{result.message}，使用等权替代")
            return np.ones(n_assets) / n_assets, np.ones(n_assets)
    except Exception as e:
        model = 'Model C' if is_relaxed else '标准RP'
        print(f"{model}异常：{e}，使用等权替代")
        return np.ones(n_assets) / n_assets, np.ones(n_assets)


def solve_leveraged_standard_rp(
        Sigma: np.ndarray, n_assets: int, bond_indices: list
) -> tuple:
    """带杠杆的标准风险平价"""
    return _optimize_with_leverage(
        Sigma, n_assets, bond_indices, is_relaxed=False
    )


def compute_annualized_params(df_period: pd.DataFrame) -> tuple:
    """计算年化参数（均值、协方差矩阵、协方差对角矩阵）"""
    freq = CONFIG["trading_days_per_year"]
    mu = df_period.mean() * freq
    Sigma = df_period.cov() * freq

    # 正则化：避免协方差矩阵奇异（提升数值稳定性）
    reg = 1e-6
    Sigma = Sigma + reg * np.eye(Sigma.shape[0])

    Theta = np.diag(np.diag(Sigma))  # 协方差矩阵的对角矩阵（仅保留单个资产方差）
    return mu.values, Sigma.values, Theta


def solve_relaxed_rp(
    Sigma: np.ndarray, mu: np.ndarray, Theta: np.ndarray, n_assets: int, R_base: float
) -> np.ndarray:
    """求解宽松风险平价权重（Model C）"""
    x_rp = solve_standard_rp(Sigma, n_assets)
    zeta0 = Sigma @ x_rp
    sigma0 = np.sqrt(x_rp @ Sigma @ x_rp)
    psi0 = sigma0 / np.sqrt(n_assets)
    gamma0 = np.min(x_rp * zeta0)
    rho0 = 0.1  # 风险调节项初始值
    v0_c = np.concatenate((x_rp, zeta0, [psi0, gamma0, rho0]))

    # 2. 自适应目标收益（论文公式：R = m·max(R_base, 0)）
    R_base = max(R_base, 0)
    R_target = CONFIG["m"] * R_base

    # 3. 目标函数（论文：min ψ - γ，无额外惩罚项，惩罚通过约束实现）
    def objective(v):
        psi = v[2 * n_assets]
        gamma = v[2 * n_assets + 1]
        return psi - gamma

    # 4. 等式约束（仅保留核心：ζ=Σx | sum(x)=1）
    def eq_constraints(v):
        x = v[:n_assets]
        zeta = v[n_assets : 2 * n_assets]
        con1 = zeta - np.dot(Sigma, x)
        con2 = np.sum(x) - 1
        return np.concatenate([con1, [con2]])

    # 5. 不等式约束（严格匹配论文Model C公式）
    def ineq_constraints(v):
        x = v[:n_assets]
        zeta = v[n_assets : 2 * n_assets]
        psi = v[2 * n_assets]
        gamma = v[2 * n_assets + 1]
        rho = v[2 * n_assets + 2]

        con1 = x * zeta - gamma**2  # 论文：x_iζ_i ≥ γ²
        con2 = rho**2 - CONFIG["lambda_pen"] * np.dot(
            x, np.dot(Theta, x)
        )  # 论文：λx^TΘx ≤ ρ²
        con3 = n_assets * (psi**2 - rho**2) - np.dot(
            x, np.dot(Sigma, x)
        )  # 论文：x^TΣx ≤ n(ψ² - ρ²)
        con4 = np.dot(mu, x) - R_target  # 论文：μ^T x ≥ R
        return np.concatenate([con1, [con2, con3, con4]])

    # 6. 优化边界（所有变量非负，符合long-only要求）
    bounds = (
        [CONFIG["asset_weight_bounds"] for _ in range(n_assets)]
        + [(0, None) for _ in range(n_assets)]
        + [(0, 10)] * 3
    )  # psi, gamma, rho的上界防止数值溢出

    # 7. 求解（关键：Model C推荐用SLSQP，原因见下文）
    try:
        result = minimize(
            objective,
            v0_c,
            method="SLSQP",  # 此处已改为与标准RP一致的SLSQP
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints},
            ],
            bounds=bounds,
            options={
                "ftol": CONFIG["optim_tol"],
                "maxiter": CONFIG["optim_maxiter"] * 2,
                "disp": False,
            },
        )

        if result.success:
            return result.x[:n_assets]
        else:
            print(f"Model C优化未收敛：{result.message}，使用标准RP权重替代")
            return x_rp
    except Exception as e:
        print(f"Model C优化异常：{e}，使用标准RP权重替代")
        return x_rp


def solve_leveraged_relaxed_rp(
    Sigma: np.ndarray, mu: np.ndarray, Theta: np.ndarray,
    n_assets: int, bond_indices: list, R_base: float
) -> tuple:
    """带杠杆的宽松风险平价（Model C）"""
    R_target = CONFIG["m"] * max(R_base, 0)
    return _optimize_with_leverage(
        Sigma, n_assets, bond_indices, mu, Theta, R_target,
        is_relaxed=True
    )


from typing import List, Tuple


def get_available_assets(
    df_returns: pd.DataFrame,
    date: pd.Timestamp,
    lookback_weeks: int,
    min_valid_data_pct: float = None,
) -> List[str]:
    """筛选指定调仓日的可用资产（排除未上市、全NaN数据的资产）"""
    window_start = date - pd.DateOffset(weeks=lookback_weeks)
    df_period = df_returns.loc[window_start:date]

    available_assets = []
    for col in df_returns.columns:
        asset_data = df_period[col].dropna()
        if not asset_data.empty:
            available_assets.append(col)

    return available_assets


def run_rolling_backtest(
    df_returns: pd.DataFrame, model_type: str = "standard"
) -> Tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
]:
    """滚动调仓回测（月度调仓），输出权重、收益、杠杆等结果"""
    lookback_weeks = CONFIG.get("lookback_weeks", 48)
    start_date = df_returns.index.min() + pd.DateOffset(weeks=lookback_weeks)
    end_date = df_returns.index.max()
    all_assets = df_returns.columns.tolist()

    # ========== 2. 生成月度调仓日 ==========
    rebalance_dates = []
    current_date = start_date
    while current_date <= end_date:
        month_first = pd.Timestamp(f"{current_date.year}-{current_date.month:02d}-01")
        month_trading_days = df_returns.index[
            (df_returns.index >= month_first)
            & (df_returns.index.year == current_date.year)
            & (df_returns.index.month == current_date.month)
        ]
        if len(month_trading_days) > 0 and month_trading_days[0] >= start_date:
            rebalance_dates.append(month_trading_days[0])
        current_date = pd.Timestamp(
            f"{current_date.year+1}-01-01"
            if current_date.month == 12
            else f"{current_date.year}-{current_date.month+1:02d}-01"
        )
    rebalance_dates = sorted(list(set(rebalance_dates)))

    # ========== 3. 初始化结果存储（新增杠杆相关） ==========
    weights_history_rp = {}
    weights_history_c = {}
    leverage_history_rp = {}  # 标准RP杠杆历史
    leverage_history_c = {}  # Model C杠杆历史
    d_mse_history = {}

    # ========== 4. 循环执行月度调仓 ==========
    for date in rebalance_dates:
        print(f"[{date.date()}] 开始调仓处理...")

        # ---------- 4.1 筛选有效资产 ----------
        available_assets = get_available_assets(df_returns, date, lookback_weeks)
        if len(available_assets) < 2:
            print(
                f"[{date.date()}] 有效资产不足2个（{len(available_assets)}个），跳过调仓"
            )
            continue

        # ---------- 4.2 提取回看期数据并补全 ----------
        window_start = date - pd.DateOffset(weeks=lookback_weeks)
        df_period = df_returns.loc[window_start:date, available_assets].copy()
        df_period = df_period.fillna(method="ffill")  # 仅前向填充，避免上市前数据污染
        if df_period.empty:
            print(f"[{date.date()}] 回看期数据为空，跳过调仓")
            continue

        # ---------- 4.3 计算年化参数 ----------
        try:
            mu, Sigma, Theta = compute_annualized_params(df_period)
            n_assets = len(available_assets)

            if n_assets != len(mu) or Sigma.shape != (n_assets, n_assets):
                print(f"[{date.date()}] 参数维度不匹配，跳过调仓")
                continue
        except Exception as e:
            print(f"[{date.date()}] 参数计算失败：{e}，跳过调仓")
            continue

        # ---------- 4.4 动态识别债券索引+求解模型（带杠杆） ----------
        try:
            bond_indices = dynamic_bond_indices(df_period)
            # 带杠杆的标准RP（返回权重+杠杆向量）
            x_rp, leverage_rp = solve_leveraged_standard_rp(
                Sigma, n_assets, bond_indices
            )

            # 根据model_type参数决定是否计算宽松风险平价模型
            if model_type == "standard":
                # 标准风险平价模型，使用标准RP的结果作为宽松RP的结果
                x_c = x_rp.copy()
                leverage_c = leverage_rp.copy()
            else:
                # 宽松风险平价模型，计算Model C
                R_base = np.dot(mu, x_rp)
                x_c, leverage_c = solve_leveraged_relaxed_rp(
                    Sigma, mu, Theta, n_assets, bond_indices, R_base
                )
        except Exception as e:
            print(f"[{date.date()}] 权重求解失败：{e}，跳过调仓")
            continue

        # ---------- 4.5 权重+杠杆回填（全资产维度） ----------
        # 权重回填（不可用资产权重为0）
        x_rp_series = pd.Series(x_rp, index=available_assets)
        x_c_series = pd.Series(x_c, index=available_assets)
        x_rp_full = x_rp_series.reindex(all_assets).fillna(0).values
        x_c_full = x_c_series.reindex(all_assets).fillna(0).values

        # 杠杆回填（非债券资产杠杆=1，不可用资产杠杆=0）
        leverage_rp_series = pd.Series(leverage_rp, index=available_assets)
        leverage_c_series = pd.Series(leverage_c, index=available_assets)
        # 非债券资产杠杆强制为1
        non_bond_assets = [
            asset
            for idx, asset in enumerate(available_assets)
            if idx not in bond_indices
        ]
        leverage_rp_series.loc[non_bond_assets] = 1.0
        leverage_c_series.loc[non_bond_assets] = 1.0
        # 全资产杠杆（不可用资产杠杆设为0，无实际意义）
        leverage_rp_full = leverage_rp_series.reindex(all_assets).fillna(0).values
        leverage_c_full = leverage_c_series.reindex(all_assets).fillna(0).values

        # ---------- 4.6 权重归一化 ----------
        rp_sum = np.sum(x_rp_full)
        c_sum = np.sum(x_c_full)
        x_rp_full = x_rp_full / rp_sum if rp_sum > 0 else x_rp_full
        x_c_full = x_c_full / c_sum if c_sum > 0 else x_c_full

        # ---------- 4.7 计算d_MSE ----------
        # 创建全资产维度的协方差矩阵（使用可用资产的协方差矩阵，不可用资产的协方差设为0）
        full_assets_count = len(all_assets)
        full_Sigma = np.zeros((full_assets_count, full_assets_count))

        # 将可用资产的协方差矩阵填充到全资产协方差矩阵中
        available_asset_indices = [
            i for i, asset in enumerate(all_assets) if asset in available_assets
        ]
        for i, available_i in enumerate(available_asset_indices):
            for j, available_j in enumerate(available_asset_indices):
                full_Sigma[available_i, available_j] = Sigma[i, j]

        # 带杠杆的风险贡献计算（贴合论文ARC定义）
        leveraged_x_rp = x_rp_full * leverage_rp_full
        sigma_rp = np.sqrt(np.dot(leveraged_x_rp, np.dot(full_Sigma, leveraged_x_rp)))
        rc_rp = (
            (leveraged_x_rp * np.dot(full_Sigma, leveraged_x_rp)) / sigma_rp
            if sigma_rp != 0
            else np.zeros_like(leveraged_x_rp)
        )

        leveraged_x_c = x_c_full * leverage_c_full
        sigma_c = np.sqrt(np.dot(leveraged_x_c, np.dot(full_Sigma, leveraged_x_c)))
        rc_c = (
            (leveraged_x_c * np.dot(full_Sigma, leveraged_x_c)) / sigma_c
            if sigma_c != 0
            else np.zeros_like(leveraged_x_c)
        )

        d_mse = np.mean((rc_c - rc_rp) ** 2)

        # ---------- 4.8 更新结果历史 ----------
        weights_history_rp[date] = x_rp_full
        weights_history_c[date] = x_c_full
        leverage_history_rp[date] = leverage_rp_full
        leverage_history_c[date] = leverage_c_full
        d_mse_history[date] = d_mse

        print(f"[{date.date()}] 调仓完成 | 有效资产数：{n_assets} | d_MSE：{d_mse:.6f}")

    # ========== 5. 结果格式化（核心补充：杠杆+带杠杆收益） ==========
    # 5.1 权重格式化（与原逻辑一致）
    weights_df_rp = pd.DataFrame(weights_history_rp).T
    if not weights_df_rp.empty:
        weights_df_rp.columns = all_assets
        weights_df_rp = weights_df_rp.reindex(df_returns.index, method="ffill").fillna(
            0
        )
        weights_df_rp = weights_df_rp.div(weights_df_rp.sum(axis=1), axis=0).fillna(0)
    else:
        weights_df_rp = pd.DataFrame(0, index=df_returns.index, columns=all_assets)

    weights_df_c = pd.DataFrame(weights_history_c).T
    if not weights_df_c.empty:
        weights_df_c.columns = all_assets
        weights_df_c = weights_df_c.reindex(df_returns.index, method="ffill").fillna(0)
        weights_df_c = weights_df_c.div(weights_df_c.sum(axis=1), axis=0).fillna(0)
    else:
        weights_df_c = pd.DataFrame(0, index=df_returns.index, columns=all_assets)

    # 5.2 杠杆历史格式化（新增）
    leverage_df_rp = pd.DataFrame(leverage_history_rp).T
    if not leverage_df_rp.empty:
        leverage_df_rp.columns = all_assets
        # 调仓间隔期杠杆保持不变（与权重一致）
        leverage_df_rp = leverage_df_rp.reindex(
            df_returns.index, method="ffill"
        ).fillna(0)
        # 非债券资产杠杆强制为1（避免数据异常）
        non_bond_indices_all = [
            i
            for i, asset in enumerate(all_assets)
            if not any(keyword in asset for keyword in CONFIG["bond_keywords"])
        ]
        leverage_df_rp.iloc[:, non_bond_indices_all] = 1.0
    else:
        leverage_df_rp = pd.DataFrame(
            1.0, index=df_returns.index, columns=all_assets
        )  # 非债券默认1.0

    leverage_df_c = pd.DataFrame(leverage_history_c).T
    if not leverage_df_c.empty:
        leverage_df_c.columns = all_assets
        leverage_df_c = leverage_df_c.reindex(df_returns.index, method="ffill").fillna(
            0
        )
        # 非债券资产杠杆强制为1（避免数据异常）
        non_bond_indices_all = [
            i
            for i, asset in enumerate(all_assets)
            if not any(keyword in asset for keyword in CONFIG["bond_keywords"])
        ]
        leverage_df_c.iloc[:, non_bond_indices_all] = 1.0
    else:
        leverage_df_c = pd.DataFrame(1.0, index=df_returns.index, columns=all_assets)

    # 5.3 组合收益计算（新增带杠杆收益，贴合论文风险-收益权衡逻辑）
    # 无杠杆收益（原逻辑）
    portfolio_returns_rp = (df_returns * weights_df_rp).sum(axis=1)
    portfolio_returns_c = (df_returns * weights_df_c).sum(axis=1)

    # 带杠杆收益（杠杆放大风险暴露，进而影响收益）
    portfolio_returns_rp_leverage = (df_returns * weights_df_rp * leverage_df_rp).sum(
        axis=1
    )
    portfolio_returns_c_leverage = (df_returns * weights_df_c * leverage_df_c).sum(
        axis=1
    )

    # 5.4 d_MSE序列格式化
    d_mse_series = pd.Series(d_mse_history)

    # ========== 6. 返回结果（新增杠杆相关输出） ==========
    return (
        weights_df_rp,
        weights_df_c,
        portfolio_returns_rp,
        portfolio_returns_c,
        d_mse_series,
        leverage_df_rp,
        leverage_df_c,  # 杠杆历史
        portfolio_returns_rp_leverage,
        portfolio_returns_c_leverage,
    )  # 带杠杆收益


def calculate_performance_metrics(
    portfolio_returns: pd.Series,
    weights_df: pd.DataFrame,
    Sigma: np.ndarray = None,
    is_leverage: bool = False,
    leverage_df: pd.DataFrame = None,
    rc_rp: np.ndarray = None,
) -> dict:
    """计算绩效指标（含杠杆效果评估）"""
    plot_start_date = pd.Timestamp(CONFIG["plot_start_date"])

    # 筛选指定日期范围内的收益数据
    portfolio_returns = portfolio_returns[portfolio_returns.index >= plot_start_date]

    # 筛选指定日期范围内的权重数据（如果需要）
    weights_df = weights_df[weights_df.index >= plot_start_date]

    # 如果是杠杆组合，也筛选杠杆数据
    if is_leverage and leverage_df is not None:
        leverage_df = leverage_df[leverage_df.index >= plot_start_date]

    freq = CONFIG["trading_days_per_year"]  # 252
    risk_free_rate = CONFIG.get(
        "risk_free_rate", 0.03
    )  # 无风险利率（默认3%，论文用10年期美债）

    # ========== 1. 传统核心指标（保留原有逻辑，优化夏普比率计算） ==========
    mean_return = portfolio_returns.mean() * freq  # 年化收益
    vol = portfolio_returns.std() * np.sqrt(freq)  # 年化波动率
    # 夏普比率：论文用“超额收益/波动率”（而非原代码的“总收益/波动率”）
    excess_return = mean_return - risk_free_rate
    sharpe = excess_return / vol if vol != 0 else 0
    # 最大回撤（原逻辑不变）
    cum_return_series = (1 + portfolio_returns).cumprod()
    max_drawdown = (1 - cum_return_series / cum_return_series.cummax()).max()
    # 累计收益、胜率
    cum_return = cum_return_series[-1] - 1
    win_rate = (portfolio_returns > 0).mean()

    # ========== 2. 论文核心指标：风险贡献距离d_MSE（Mean-Squared-Error） ==========
    d_mse = np.nan
    if Sigma is not None and rc_rp is not None and not weights_df.empty:
        # 取最新一期权重计算当前组合的风险贡献（ARC）
        latest_weights = weights_df.iloc[-1].values.reshape(-1, 1)
        # 计算带杠杆的风险暴露（若为杠杆组合）
        if is_leverage and leverage_df is not None:
            latest_leverage = leverage_df.iloc[-1].values.reshape(-1, 1)
            leveraged_weights = latest_weights * latest_leverage
        else:
            leveraged_weights = latest_weights

        # 计算组合波动率
        portfolio_vol = np.sqrt(
            np.dot(leveraged_weights.T, np.dot(Sigma, leveraged_weights))
        )[0, 0]
        if portfolio_vol != 0:
            # 计算当前组合的绝对风险贡献（ARC），贴合论文公式σ_i(x) = [x_i(Σx)_i]/√(x^TΣx)
            rc_current = (
                leveraged_weights * np.dot(Sigma, leveraged_weights)
            ) / portfolio_vol
            # 计算与标准RP风险贡献的MSE（论文定义的距离指标）
            d_mse = np.mean((rc_current.flatten() - rc_rp.flatten()) ** 2)

    # ========== 3. 杠杆效果专属指标（仅带杠杆组合计算） ==========
    avg_leverage = np.nan
    leverage_volatility = np.nan
    if is_leverage and leverage_df is not None:
        # 债券资产平均杠杆（论文关注低风险资产杠杆使用情况）
        bond_keywords = CONFIG["bond_keywords"]
        bond_assets = [
            col
            for col in leverage_df.columns
            if any(keyword in col for keyword in bond_keywords)
        ]
        if bond_assets:
            avg_leverage = (
                leverage_df[bond_assets].mean().mean()
            )  # 所有债券资产的平均杠杆
            leverage_volatility = (
                leverage_df[bond_assets].std().mean()
            )  # 杠杆波动（衡量杠杆稳定性）

    # ========== 4. 换手率指标计算 ==========
    monthly_turnover = np.nan
    annual_avg_turnover = np.nan
    if not weights_df.empty:
        try:
            # 计算月度换手率
            # 1. 按月分组
            monthly_weights = weights_df.resample("M").last()
            if len(monthly_weights) > 1:
                # 2. 计算每月权重变化的绝对值之和，除以2（因为买入和卖出都计算了一次）
                weight_changes = monthly_weights.diff().abs().sum(axis=1) / 2
                # 3. 排除第一个月（没有前一个月数据）
                monthly_turnover = weight_changes.iloc[1:].mean()

                # 计算年平均换手率
                # 1. 按年分组
                annual_turnover = monthly_weights.resample("A").last()
                if len(annual_turnover) > 1:
                    # 2. 计算每年权重变化的绝对值之和，除以2
                    annual_weight_changes = annual_turnover.diff().abs().sum(axis=1) / 2
                    # 3. 排除第一年
                    annual_avg_turnover = annual_weight_changes.iloc[1:].mean()
        except Exception as e:
            print(f"计算换手率时出错: {e}")

    # ========== 4. 整合输出指标 ==========
    metrics = {
        "累计收益": round(cum_return, 4),
        "年化收益": round(mean_return, 4),
        "年化波动率": round(vol, 4),
        "夏普比率": round(sharpe, 4),  # 已修正为论文要求的“超额收益/波动率”
        "最大回撤": round(max_drawdown, 4),
        "胜率": round(win_rate, 4),
        "月度换手率": (
            round(monthly_turnover, 4) if not np.isnan(monthly_turnover) else np.nan
        ),
        "年平均换手率": (
            round(annual_avg_turnover, 4)
            if not np.isnan(annual_avg_turnover)
            else np.nan
        ),
        "风险贡献距离d_MSE": (
            round(d_mse, 6) if not np.isnan(d_mse) else np.nan
        ),  # 论文核心指标
    }

    # 新增杠杆相关指标（带杠杆组合专属）
    if is_leverage:
        metrics.update(
            {
                "债券平均杠杆": (
                    round(avg_leverage, 4) if not np.isnan(avg_leverage) else np.nan
                ),
                "杠杆波动率": (
                    round(leverage_volatility, 4)
                    if not np.isnan(leverage_volatility)
                    else np.nan
                ),
                "风险调整后收益（夏普比率）": round(
                    sharpe, 4
                ),  # 重复标注，强调论文关注的风险调整指标
            }
        )

    return metrics


# 辅助函数：计算标准RP的风险贡献（用于d_MSE计算）
def calculate_rp_risk_contribution(
    Sigma: np.ndarray, rp_weights: np.ndarray
) -> np.ndarray:
    """
    计算标准风险平价组合的绝对风险贡献（ARC），贴合论文公式
    输入：
        Sigma: 年化协方差矩阵
        rp_weights: 标准RP的资产权重
    输出：
        rc_rp: 各资产的风险贡献（与资产数量一致）
    """
    rp_weights = rp_weights.reshape(-1, 1)
    portfolio_vol = np.sqrt(np.dot(rp_weights.T, np.dot(Sigma, rp_weights)))[0, 0]
    if portfolio_vol == 0:
        return np.zeros_like(rp_weights).flatten()
    # 论文公式：σ_i(x) = [x_i(Σx)_i]/√(x^TΣx)
    rc_rp = (rp_weights * np.dot(Sigma, rp_weights)) / portfolio_vol
    return rc_rp.flatten()


from typing import Tuple


def setup_date_axis(ax, start_date, end_date):
    """
    统一设置X轴日期格式，确保每个月都能清晰显示
    """
    # 设置主刻度为每个月
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    # 设置日期格式为 年-月
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # 旋转标签90度，字体调小一点以防重叠
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=8)

    # 设置X轴范围，稍微留一点余地或者精确对齐
    ax.set_xlim(start_date, end_date)

    # 开启网格，x轴网格对应每个月
    ax.grid(True, which="major", axis="x", alpha=0.3, linestyle="--")


def plot_results(
    df_returns: pd.DataFrame,
    weights_df_rp: pd.DataFrame,
    weights_df_c: pd.DataFrame,
    portfolio_returns_rp: pd.Series,
    portfolio_returns_c: pd.Series,
    d_mse_series: pd.Series,
    asset_df: pd.DataFrame = None,
    leverage_df_rp: pd.DataFrame = None,
    leverage_df_c: pd.DataFrame = None,
    portfolio_returns_rp_leverage: pd.Series = None,
    portfolio_returns_c_leverage: pd.Series = None,
    output_folder: str = "rp_model_plots",
):
    """可视化结果（适配杠杆+核心指标）"""
    plot_start = pd.Timestamp(CONFIG["plot_start_date"])
    ten_year_bond_col = "CFFEX10年期国债期货"
    bond_keywords = CONFIG["bond_keywords"]  # 债券识别关键词

    # ========== 数据预处理（统一筛选+杠杆数据适配） ==========
    # 1. 基础收益数据筛选
    portfolio_returns_rp_filtered = portfolio_returns_rp[
        portfolio_returns_rp.index >= plot_start
    ]
    portfolio_returns_c_filtered = portfolio_returns_c[
        portfolio_returns_c.index >= plot_start
    ]
    # 带杠杆收益筛选（若存在）
    has_leverage = (
        leverage_df_rp is not None and portfolio_returns_rp_leverage is not None
    )
    if has_leverage:
        portfolio_returns_rp_leverage_filtered = portfolio_returns_rp_leverage[
            portfolio_returns_rp_leverage.index >= plot_start
        ]
        portfolio_returns_c_leverage_filtered = portfolio_returns_c_leverage[
            portfolio_returns_c_leverage.index >= plot_start
        ]
        # 债券资产筛选（用于杠杆趋势图）
        bond_assets = [
            col
            for col in leverage_df_rp.columns
            if any(keyword in col for keyword in bond_keywords)
        ]

    # 2. 国债期货数据适配（允许asset_df为空）
    ten_year_bond_returns_filtered = None
    if (
        asset_df is not None
        and ten_year_bond_col in asset_df.columns
        and "date" in asset_df.columns
    ):
        asset_df_copy = asset_df.copy()
        asset_df_copy["date"] = pd.to_datetime(asset_df_copy["date"])
        asset_df_copy = asset_df_copy.sort_values(by="date").reset_index(drop=True)
        asset_df_copy["ten_year_bond_return"] = asset_df_copy[
            ten_year_bond_col
        ].pct_change()
        asset_df_filtered = asset_df_copy[asset_df_copy["date"] >= plot_start].dropna(
            subset=["ten_year_bond_return"]
        )
        ten_year_bond_temp = asset_df_filtered.set_index("date")["ten_year_bond_return"]
        ten_year_bond_returns = ten_year_bond_temp.reindex(
            portfolio_returns_rp.index, fill_value=0
        )
        ten_year_bond_returns_filtered = ten_year_bond_returns[
            ten_year_bond_returns.index >= plot_start
        ]

    # 创建输出文件夹
    import os

    os.makedirs(output_folder, exist_ok=True)

    # 确保所有子文件夹存在
    os.makedirs(os.path.join(output_folder), exist_ok=True)

    # ========== 图表1：累计收益对比（含带杠杆版本） ==========
    plt.figure(figsize=(14, 7))

    # 计算累计收益并确保第一天净值为1
    cum_rp = (1 + portfolio_returns_rp_filtered).cumprod()
    cum_rp.iloc[0] = 1  # 第一天净值设为1
    cum_rp.plot(label="标准RP（无杠杆）", linewidth=2)

    cum_c = (1 + portfolio_returns_c_filtered).cumprod()
    cum_c.iloc[0] = 1  # 第一天净值设为1
    cum_c.plot(label="宽松RP（无杠杆）", linewidth=2)

    if has_leverage:
        cum_rp_leverage = (1 + portfolio_returns_rp_leverage_filtered).cumprod()
        cum_rp_leverage.iloc[0] = 1  # 第一天净值设为1
        cum_rp_leverage.plot(label="标准RP（带杠杆）", linewidth=2, linestyle="--")

        cum_c_leverage = (1 + portfolio_returns_c_leverage_filtered).cumprod()
        cum_c_leverage.iloc[0] = 1  # 第一天净值设为1
        cum_c_leverage.plot(label="宽松RP（带杠杆）", linewidth=2, linestyle="--")

    if ten_year_bond_returns_filtered is not None:
        cum_bond = (1 + ten_year_bond_returns_filtered).cumprod()
        cum_bond.iloc[0] = 1  # 第一天净值设为1
        cum_bond.plot(label=ten_year_bond_col, linestyle=":", linewidth=2)
    plt.title(
        f"组合累计收益（{plot_start.strftime('%Y-%m-%d')} 至 最新）",
        fontsize=14,
        fontweight="bold",
    )
    plt.ylabel("累计收益", fontsize=12)
    plt.legend(fontsize=11)

    # 设置X轴日期格式
    setup_date_axis(plt.gca(), plot_start, portfolio_returns_rp_filtered.index[-1])

    plt.tight_layout()
    plt.savefig(
        os.path.join(output_folder, "组合累计收益对比.png"),
        dpi=300,
        bbox_inches="tight",
    )

    # ========== 图表2：债券杠杆变化趋势（适配带杠杆模型） ==========
    if has_leverage and bond_assets:
        plt.figure(figsize=(14, 7))
        # 计算双模型的债券平均杠杆
        leverage_rp_avg = leverage_df_rp[bond_assets].mean(axis=1)  # 单期债券平均杠杆
        leverage_c_avg = leverage_df_c[bond_assets].mean(axis=1)
        # 筛选时间区间
        leverage_rp_avg_filtered = leverage_rp_avg[leverage_rp_avg.index >= plot_start]
        leverage_c_avg_filtered = leverage_c_avg[leverage_c_avg.index >= plot_start]
        # 绘图
        leverage_rp_avg_filtered.plot(
            label="标准RP - 债券平均杠杆", linewidth=2, color="steelblue"
        )
        leverage_c_avg_filtered.plot(
            label="宽松RP - 债券平均杠杆", linewidth=2, color="coral"
        )
        plt.axhline(y=1.0, color="black", linestyle="--", alpha=0.5, label="无杠杆基准")
        plt.title(
            f"债券资产平均杠杆变化（{plot_start.strftime('%Y-%m-%d')} 至 最新）",
            fontsize=14,
            fontweight="bold",
        )
        plt.ylabel("平均杠杆倍数", fontsize=12)
        plt.ylim(bottom=0.9)  # 杠杆最低接近1，避免图表拉伸
        plt.legend(fontsize=11)

        # 设置X轴日期格式
        setup_date_axis(plt.gca(), plot_start, leverage_rp_avg_filtered.index[-1])

        plt.tight_layout()
        plt.savefig(
            os.path.join(output_folder, "债券资产平均杠杆变化.png"),
            dpi=300,
            bbox_inches="tight",
        )

    # ========== 图表3：资产权重变化（聚合+单资产可选） ==========
    def plot_weight_evolution(
        weights_df: pd.DataFrame, title_suffix: str, color_base: str
    ):
        weights_filtered = (
            weights_df[weights_df.index >= plot_start].clip(lower=0).fillna(0)
        )
        weights_filtered = weights_filtered.div(
            weights_filtered.sum(axis=1), axis=0
        ).fillna(0)

        # 资产类别聚合（债券/非债券）
        bond_mask = [
            any(keyword in col for keyword in bond_keywords)
            for col in weights_filtered.columns
        ]
        weights_bond = weights_filtered.iloc[:, bond_mask].sum(axis=1)
        # 将bond_mask转换为numpy数组，然后应用~操作符
        import numpy as np

        bond_mask_np = np.array(bond_mask)
        weights_non_bond = weights_filtered.iloc[:, ~bond_mask_np].sum(axis=1)

        # 绘图（先聚合，后单资产可选）
        plt.figure(figsize=(16, 9))
        # 类别聚合堆叠图
        weights_agg = pd.DataFrame(
            {"债券类资产": weights_bond, "非债券类资产": weights_non_bond}
        )
        weights_agg.plot.area(
            stacked=True, linewidth=1, color=[color_base, "lightgray"]
        )
        plt.title(
            f"{title_suffix} - 资产类别权重变化（{plot_start.strftime('%Y-%m-%d')} 至 最新）",
            fontsize=14,
            fontweight="bold",
        )
        plt.ylabel("权重占比", fontsize=12)
        plt.legend(fontsize=11, bbox_to_anchor=(1.05, 1), loc="upper left")

        # 设置X轴日期格式
        setup_date_axis(plt.gca(), plot_start, weights_filtered.index[-1])

        plt.tight_layout()
        plt.savefig(
            os.path.join(output_folder, f"{title_suffix}_资产类别权重变化.png"),
            dpi=300,
            bbox_inches="tight",
        )

    plot_weight_evolution(weights_df_rp, "标准RP", "steelblue")
    plot_weight_evolution(weights_df_c, "宽松RP", "coral")

    # ========== 图表4：风险贡献距离d_MSE（新增阈值线） ==========
    d_mse_series_filtered = d_mse_series[d_mse_series.index >= plot_start]
    plt.figure(figsize=(14, 7))
    d_mse_series_filtered.plot(color="crimson", linewidth=2, marker="o", markersize=4)
    # 新增论文参考阈值（根据Table 3设置）
    plt.axhline(
        y=0.05, color="orange", linestyle="--", alpha=0.7, label="合理偏离阈值（0.05）"
    )
    plt.axhline(y=0.1, color="red", linestyle="--", alpha=0.7, label="警戒阈值（0.1）")
    plt.title(
        f"风险贡献距离（d_MSE，{plot_start.strftime('%Y-%m-%d')} 至 最新）",
        fontsize=14,
        fontweight="bold",
    )
    plt.ylabel("d_MSE", fontsize=12)
    plt.ylim(bottom=0)
    plt.legend(fontsize=11)

    # 设置X轴日期格式
    setup_date_axis(plt.gca(), plot_start, d_mse_series_filtered.index[-1])

    plt.tight_layout()
    plt.savefig(
        os.path.join(output_folder, "风险贡献距离d_MSE.png"),
        dpi=300,
        bbox_inches="tight",
    )

    # ========== 图表5：风险-收益散点图（新增，契合论文有效前沿） ==========
    def calculate_period_risk_return(
        returns: pd.Series, period: str = "M"
    ) -> Tuple[pd.Series, pd.Series]:
        """计算周期化风险-收益"""
        period_returns = returns.resample(period).apply(lambda x: (1 + x).prod() - 1)
        period_risk = returns.resample(period).std() * np.sqrt(
            CONFIG["trading_days_per_year"] / 12
        )  # 月度年化波动率
        return period_risk, period_returns * 12  # 月度收益年化

    plt.figure(figsize=(12, 8))
    # 计算双模型月度风险-收益
    rp_risk, rp_return = calculate_period_risk_return(portfolio_returns_rp_filtered)
    c_risk, c_return = calculate_period_risk_return(portfolio_returns_c_filtered)
    # 散点图
    plt.scatter(rp_risk, rp_return, color="steelblue", label="标准RP", s=50, alpha=0.7)
    plt.scatter(c_risk, c_return, color="coral", label="宽松RP", s=50, alpha=0.7)
    # 标注最新点
    if not rp_risk.empty:
        plt.scatter(
            rp_risk.iloc[-1],
            rp_return.iloc[-1],
            color="blue",
            s=100,
            marker="*",
            label="标准RP（最新）",
        )
    if not c_risk.empty:
        plt.scatter(
            c_risk.iloc[-1],
            c_return.iloc[-1],
            color="red",
            s=100,
            marker="*",
            label="宽松RP（最新）",
        )
    plt.title(
        f"风险-收益分布（月度年化，{plot_start.strftime('%Y-%m-%d')} 至 最新）",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("年化波动率", fontsize=12)
    plt.ylabel("年化收益", fontsize=12)
    plt.legend(fontsize=11)
    plt.grid(alpha=0.3, linestyle="--")
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_folder, "风险-收益散点图.png"), dpi=300, bbox_inches="tight"
    )


def plot_risk_contribution(
    weights_df_rp: pd.DataFrame,
    weights_df_c: pd.DataFrame,
    df_returns: pd.DataFrame,
    leverage_df_rp: pd.DataFrame = None,
    leverage_df_c: pd.DataFrame = None,
    output_folder: str = "rp_model_plots",
):
    """可视化最新调仓风险贡献（适配杠杆）"""
    plot_start = pd.Timestamp(CONFIG["plot_start_date"])
    bond_keywords = CONFIG["bond_keywords"]

    # 数据筛选与最新日期确定
    weights_df_rp_filtered = weights_df_rp[weights_df_rp.index >= plot_start]
    weights_df_c_filtered = weights_df_c[weights_df_c.index >= plot_start]
    latest_date = max(
        (
            weights_df_rp_filtered.index[-1]
            if not weights_df_rp_filtered.empty
            else weights_df_rp.index[-1]
        ),
        (
            weights_df_c_filtered.index[-1]
            if not weights_df_c_filtered.empty
            else weights_df_c.index[-1]
        ),
    )

    # 计算最新协方差矩阵
    window_start = latest_date - pd.DateOffset(weeks=CONFIG["lookback_weeks"])
    df_period = df_returns.loc[window_start:latest_date]
    if df_period.empty:
        raise ValueError("回看数据为空，无法计算风险贡献")
    _, Sigma, _ = compute_annualized_params(df_period)
    n_assets = Sigma.shape[0]
    ideal_rc = 1 / n_assets  # 理想风险贡献（等权风险）

    # 风险贡献计算（适配杠杆）
    def compute_rc(
        weights_df: pd.DataFrame, leverage_df: pd.DataFrame = None
    ) -> pd.Series:
        latest_weights = weights_df.loc[latest_date].values
        if leverage_df is not None:
            latest_leverage = leverage_df.loc[latest_date].values
            leveraged_weights = latest_weights * latest_leverage
        else:
            leveraged_weights = latest_weights
        sigma_p = np.sqrt(leveraged_weights @ Sigma @ leveraged_weights)
        rc = (leveraged_weights * (Sigma @ leveraged_weights)) / sigma_p
        return pd.Series(rc, index=weights_df.columns)

    rc_rp = compute_rc(weights_df_rp, leverage_df_rp)
    rc_c = compute_rc(weights_df_c, leverage_df_c)

    # 绘图（双模型对比，新增理想风险线）
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), sharex=True)
    # 标准RP
    rc_rp_sorted = rc_rp.sort_values(ascending=False)
    ax1.bar(range(len(rc_rp_sorted)), rc_rp_sorted.values, color="steelblue", alpha=0.8)
    ax1.axhline(
        y=ideal_rc,
        color="red",
        linestyle="--",
        alpha=0.7,
        label=f"理想风险贡献（{ideal_rc:.4f}）",
    )
    ax1.set_title(
        f"标准RP - 最新调仓风险贡献（{latest_date.strftime('%Y-%m-%d')}）",
        fontsize=14,
        fontweight="bold",
    )
    ax1.set_ylabel("风险贡献占比", fontsize=12)
    ax1.legend(fontsize=11)
    ax1.grid(alpha=0.3, linestyle="--")
    # 宽松RP
    rc_c_sorted = rc_c.sort_values(ascending=False)
    ax2.bar(range(len(rc_c_sorted)), rc_c_sorted.values, color="coral", alpha=0.8)
    ax2.axhline(
        y=ideal_rc,
        color="red",
        linestyle="--",
        alpha=0.7,
        label=f"理想风险贡献（{ideal_rc:.4f}）",
    )
    ax2.set_title(
        f"宽松RP - 最新调仓风险贡献（{latest_date.strftime('%Y-%m-%d')}）",
        fontsize=14,
        fontweight="bold",
    )
    ax2.set_ylabel("风险贡献占比", fontsize=12)
    ax2.set_xlabel("资产排序（按风险贡献降序）", fontsize=12)
    ax2.legend(fontsize=11)
    ax2.grid(alpha=0.3, linestyle="--")
    plt.tight_layout()

    # 创建输出文件夹并保存图片
    import os

    os.makedirs(output_folder, exist_ok=True)
    plt.savefig(
        os.path.join(output_folder, "最新调仓风险贡献.png"),
        dpi=300,
        bbox_inches="tight",
    )


def plot_performance_comparison(
    metrics_rp: dict,
    metrics_c: dict,
    metrics_rp_leverage: dict = None,
    metrics_c_leverage: dict = None,
    output_folder: str = "rp_model_plots",
):
    """绩效指标对比图"""
    core_metrics = [
        "年化收益",
        "年化波动率",
        "夏普比率",
        "最大回撤",
        "风险贡献距离d_MSE",
    ]
    if metrics_rp_leverage is not None:
        models = [
            "标准RP（无杠杆）",
            "标准RP（带杠杆）",
            "宽松RP（无杠杆）",
            "宽松RP（带杠杆）",
        ]
        metrics_list = [metrics_rp, metrics_rp_leverage, metrics_c, metrics_c_leverage]
    else:
        models = ["标准RP", "宽松RP"]
        metrics_list = [metrics_rp, metrics_c]

    # 数据整理（统一指标顺序）
    data = []
    for metrics in metrics_list:
        metrics_clean = {k: metrics.get(k, 0) for k in core_metrics}
        # 最大回撤转为正值（便于展示）
        metrics_clean["最大回撤"] = abs(metrics_clean["最大回撤"])
        data.append(list(metrics_clean.values()))

    # 柱状图
    fig, ax = plt.subplots(figsize=(14, 8))
    x = np.arange(len(core_metrics))
    width = 0.2  # 柱子宽度
    for i, (model, values) in enumerate(zip(models, data)):
        ax.bar(
            x + i * width - width * (len(models) - 1) / 2,
            values,
            width,
            label=model,
            alpha=0.8,
        )

    # 图表美化
    ax.set_title("双模型核心绩效指标对比", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(core_metrics, rotation=45, ha="right")
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3, linestyle="--", axis="y")
    plt.tight_layout()

    # 创建输出文件夹并保存图片
    import os

    os.makedirs(output_folder, exist_ok=True)
    plt.savefig(
        os.path.join(output_folder, "双模型核心绩效指标对比.png"),
        dpi=300,
        bbox_inches="tight",
    )


def main(
    file_path: str = "rp_model_input.csv",
    asset_df_path: str = None,
    model_type: str = "standard",
    output_folder: str = "rp_model_plots",
):
    """主流程：加载数据、回测、绩效分析、可视化"""
    import os

    file_path = str(_resolve_path(file_path))
    asset_df_path = str(_resolve_path(asset_df_path)) if asset_df_path else None
    output_folder = str(_resolve_path(output_folder))

    # 创建输出文件夹
    os.makedirs(output_folder, exist_ok=True)

    # 确保所有子文件夹存在
    os.makedirs(os.path.join(output_folder), exist_ok=True)

    # 1. 数据加载
    print("===== 1. 数据加载与预处理 =====")
    df_returns = load_and_preprocess_data(file_path)
    # 加载国债期货数据（可选）
    asset_df = pd.read_csv(asset_df_path) if asset_df_path else None
    print(
        f"数据时间范围：{df_returns.index.min().date()} ~ {df_returns.index.max().date()}"
    )
    print(f"资产数量：{df_returns.shape[1]} | 日度样本量：{len(df_returns)}")
    print("-" * 50)

    # 2. 滚动回测（接收杠杆相关返回值）
    print("===== 2. 滚动调仓回测 =====")
    # 注意：需修改 run_rolling_backtest 返回值，包含杠杆和带杠杆收益
    results = run_rolling_backtest(df_returns, model_type=model_type)
    if len(results) == 9:
        (
            weights_df_rp,
            weights_df_c,
            portfolio_returns_rp,
            portfolio_returns_c,
            d_mse_series,
            leverage_df_rp,
            leverage_df_c,
            portfolio_returns_rp_leverage,
            portfolio_returns_c_leverage,
        ) = results
        has_leverage = True
    else:
        (
            weights_df_rp,
            weights_df_c,
            portfolio_returns_rp,
            portfolio_returns_c,
            d_mse_series,
        ) = results
        leverage_df_rp = leverage_df_c = portfolio_returns_rp_leverage = (
            portfolio_returns_c_leverage
        ) = None
        has_leverage = False
    print("-" * 50)

    # 3. 绩效分析（含带杠杆版本）
    print("===== 3. 绩效指标 =====")
    metrics_rp = calculate_performance_metrics(portfolio_returns_rp, weights_df_rp)
    metrics_c = calculate_performance_metrics(portfolio_returns_c, weights_df_c)
    metrics_rp_leverage = metrics_c_leverage = None
    if has_leverage:
        metrics_rp_leverage = calculate_performance_metrics(
            portfolio_returns_rp_leverage,
            weights_df_rp,
            is_leverage=True,
            leverage_df=leverage_df_rp,
        )
        metrics_c_leverage = calculate_performance_metrics(
            portfolio_returns_c_leverage,
            weights_df_c,
            is_leverage=True,
            leverage_df=leverage_df_c,
        )
    # 打印绩效（略，保持原逻辑）
    print("-" * 50)

    # 4. 可视化（新增绩效对比+适配杠杆）
    print("===== 4. 核心结果可视化 =====")
    plot_results(
        df_returns,
        weights_df_rp,
        weights_df_c,
        portfolio_returns_rp,
        portfolio_returns_c,
        d_mse_series,
        asset_df,
        leverage_df_rp,
        leverage_df_c,
        portfolio_returns_rp_leverage,
        portfolio_returns_c_leverage,
        output_folder=output_folder,
    )

    print("===== 5. 风险贡献可视化 =====")
    plot_risk_contribution(
        weights_df_rp,
        weights_df_c,
        df_returns,
        leverage_df_rp,
        leverage_df_c,
        output_folder=output_folder,
    )

    print("===== 6. 绩效指标对比可视化 =====")
    plot_performance_comparison(
        metrics_rp,
        metrics_c,
        metrics_rp_leverage,
        metrics_c_leverage,
        output_folder=output_folder,
    )

    print("===== 回测完成 =====")

    # 输出持仓结果和绩效指标到Excel
    print("===== 输出结果到Excel ======")
    output_file = os.path.join(output_folder, "rp_backtest_results.xlsx")

    # 计算从2020-01-01开始的净值
    start_date = pd.Timestamp("2020-01-01")

    # 标准RP净值（向量化优化）
    portfolio_returns_rp_filtered = portfolio_returns_rp[
        portfolio_returns_rp.index >= start_date
    ]
    if not portfolio_returns_rp_filtered.empty:
        portfolio_nav_rp = (1 + portfolio_returns_rp_filtered).cumprod()
        portfolio_nav_rp.iloc[0] = 1.0
        portfolio_nav_rp.name = "净值"
    else:
        portfolio_nav_rp = pd.Series([], name="净值")

    # 宽松RP净值（向量化优化）
    portfolio_returns_c_filtered = portfolio_returns_c[
        portfolio_returns_c.index >= start_date
    ]
    if not portfolio_returns_c_filtered.empty:
        portfolio_nav_c = (1 + portfolio_returns_c_filtered).cumprod()
        portfolio_nav_c.iloc[0] = 1.0
        portfolio_nav_c.name = "净值"
    else:
        portfolio_nav_c = pd.Series([], name="净值")

    # 标准RP带杠杆净值（向量化优化）
    portfolio_nav_rp_leverage = None
    if has_leverage:
        portfolio_returns_rp_leverage_filtered = portfolio_returns_rp_leverage[
            portfolio_returns_rp_leverage.index >= start_date
        ]
        if not portfolio_returns_rp_leverage_filtered.empty:
            portfolio_nav_rp_leverage = (
                1 + portfolio_returns_rp_leverage_filtered
            ).cumprod()
            portfolio_nav_rp_leverage.iloc[0] = 1.0
            portfolio_nav_rp_leverage.name = "净值"

    # 宽松RP带杠杆净值（向量化优化）
    portfolio_nav_c_leverage = None
    if has_leverage:
        portfolio_returns_c_leverage_filtered = portfolio_returns_c_leverage[
            portfolio_returns_c_leverage.index >= start_date
        ]
        if not portfolio_returns_c_leverage_filtered.empty:
            portfolio_nav_c_leverage = (
                1 + portfolio_returns_c_leverage_filtered
            ).cumprod()
            portfolio_nav_c_leverage.iloc[0] = 1.0
            portfolio_nav_c_leverage.name = "净值"

    # 计算大类资产权重
    asset_classes = {
        "黄金": ["黄金ETF"],
        "商品": ["有色ETF大成"],
        "港股": ["恒生科技指数ETF", "恒生ETF"],
        "A股": [
            "沪深300ETF华泰柏瑞",
            "上证指数ETF",
            "中证1000ETF",
            "科创50ETF",
            "红利ETF",
        ],
        "海外": ["纳指ETF", "标普500ETF", "日经225ETF"],
        "债券": [
            "0-5中高信用票",
            "CFFEX10年期国债期货",
            "CFFEX2年期国债期货",
            "CFFEX30年期国债期货",
        ],
    }

    def calculate_asset_class_weights(weights_df, asset_classes):
        """计算大类资产权重"""
        asset_class_weights = pd.DataFrame(index=weights_df.index)
        for asset_class, assets in asset_classes.items():
            class_assets = [asset for asset in assets if asset in weights_df.columns]
            if class_assets:
                asset_class_weights[asset_class] = weights_df[class_assets].sum(axis=1)
        # 归一化
        asset_class_weights = asset_class_weights.div(
            asset_class_weights.sum(axis=1), axis=0
        ).fillna(0)
        return asset_class_weights

    # 计算大类资产权重
    asset_class_weights_rp = calculate_asset_class_weights(weights_df_rp, asset_classes)
    asset_class_weights_c = calculate_asset_class_weights(weights_df_c, asset_classes)

    # 准备风险收益散点图数据
    risk_return_data = pd.DataFrame(
        {
            "模型": ["标准RP", "宽松RP"],
            "年化收益": [metrics_rp["年化收益"], metrics_c["年化收益"]],
            "年化波动率": [metrics_rp["年化波动率"], metrics_c["年化波动率"]],
            "夏普比率": [metrics_rp["夏普比率"], metrics_c["夏普比率"]],
        }
    )

    if has_leverage:
        leverage_risk_return_data = pd.DataFrame(
            {
                "模型": ["标准RP带杠杆", "宽松RP带杠杆"],
                "年化收益": [
                    metrics_rp_leverage["年化收益"],
                    metrics_c_leverage["年化收益"],
                ],
                "年化波动率": [
                    metrics_rp_leverage["年化波动率"],
                    metrics_c_leverage["年化波动率"],
                ],
                "夏普比率": [
                    metrics_rp_leverage["夏普比率"],
                    metrics_c_leverage["夏普比率"],
                ],
            }
        )
        risk_return_data = pd.concat(
            [risk_return_data, leverage_risk_return_data], ignore_index=True
        )

    # 使用openpyxl引擎，不需要额外安装模块
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        # 1. 输出持仓权重结果
        weights_df_rp.to_excel(writer, sheet_name="标准RP权重")
        weights_df_c.to_excel(writer, sheet_name="宽松RP权重")

        # 2. 输出组合收益
        portfolio_returns_rp.to_frame(name="组合收益").to_excel(
            writer, sheet_name="标准RP收益"
        )
        portfolio_returns_c.to_frame(name="组合收益").to_excel(
            writer, sheet_name="宽松RP收益"
        )

        # 3. 输出净值结果（从2020-01-01开始）
        portfolio_nav_rp.to_frame().to_excel(writer, sheet_name="标准RP净值")
        portfolio_nav_c.to_frame().to_excel(writer, sheet_name="宽松RP净值")
        if has_leverage:
            portfolio_nav_rp_leverage.to_frame().to_excel(
                writer, sheet_name="标准RP带杠杆净值"
            )
            portfolio_nav_c_leverage.to_frame().to_excel(
                writer, sheet_name="宽松RP带杠杆净值"
            )

        # 4. 输出大类资产权重
        asset_class_weights_rp.to_excel(writer, sheet_name="标准RP大类资产权重")
        asset_class_weights_c.to_excel(writer, sheet_name="宽松RP大类资产权重")

        # 5. 输出绩效指标
        metrics_df = pd.DataFrame({"标准RP": metrics_rp, "宽松RP": metrics_c}).T
        metrics_df.to_excel(writer, sheet_name="绩效指标对比")

        # 6. 输出风险收益散点图数据
        risk_return_data.to_excel(writer, sheet_name="风险收益数据", index=False)

        # 7. 如果有杠杆，输出杠杆相关结果
        if has_leverage:
            leverage_df_rp.to_excel(writer, sheet_name="标准RP杠杆")
            leverage_df_c.to_excel(writer, sheet_name="宽松RP杠杆")
            portfolio_returns_rp_leverage.to_frame(name="组合收益").to_excel(
                writer, sheet_name="标准RP带杠杆收益"
            )
            portfolio_returns_c_leverage.to_frame(name="组合收益").to_excel(
                writer, sheet_name="宽松RP带杠杆收益"
            )

            # 输出带杠杆的绩效指标
            leverage_metrics_df = pd.DataFrame(
                {
                    "标准RP带杠杆": metrics_rp_leverage,
                    "宽松RP带杠杆": metrics_c_leverage,
                }
            ).T
            leverage_metrics_df.to_excel(writer, sheet_name="带杠杆绩效指标")

    print(f"结果已输出到：{output_file}")

    # 5. 生成用户定制图表
    print("===== 7. 生成用户定制图表 =====")

    # 确保asset_df不为None，用于10年期国债期货对比
    if asset_df is None:
        print("重新加载原始数据用于国债期货对比")
        try:
            asset_df = pd.read_csv(file_path)
            print(f"原始数据加载成功，样本数量: {len(asset_df)}")
        except Exception as e:
            print(f"无法加载原始数据: {e}，跳过国债期货对比图")

    if asset_df is not None:
        print("正在生成国债期货对比图...")
        plot_portfolio_vs_bond(
            portfolio_returns_rp,
            portfolio_returns_c,
            asset_df,
            output_folder=output_folder,
            portfolio_returns_rp_leverage=portfolio_returns_rp_leverage,
            portfolio_returns_c_leverage=portfolio_returns_c_leverage,
        )

    print("正在生成模型权重对比图...")
    plot_model_weights_comparison(
        weights_df_rp, weights_df_c, output_folder=output_folder
    )

    print("正在生成大类资产配置变化图...")
    plot_asset_class_evolution(weights_df_rp, weights_df_c, output_folder=output_folder)

    # 绘制风险收益散点图
    print("正在生成风险收益散点图...")
    plot_risk_return_scatter(risk_return_data, output_folder=output_folder)

    print(f"所有图表已保存到 {output_folder} 文件夹")
    print(f"\n===================== 回测完成 =====================")
    print(f"版本: {os.path.basename(output_folder)}")
    print(f"模型类型: {'标准风险平价' if model_type == 'standard' else '宽松风险平价'}")
    print(f"结果保存路径: {output_folder}")


def plot_risk_return_scatter(risk_return_data, output_folder="rp_model_plots"):
    """绘制风险收益散点图"""
    import os
    import matplotlib.pyplot as plt

    # 确保输出文件夹存在
    os.makedirs(output_folder, exist_ok=True)

    # 绘制散点图
    plt.figure(figsize=(12, 8))

    # 不同模型类型的颜色
    colors = {
        "标准RP": "blue",
        "宽松RP": "green",
        "标准RP带杠杆": "red",
        "宽松RP带杠杆": "orange",
    }

    # 绘制每个点
    for _, row in risk_return_data.iterrows():
        model = row["模型"]
        plt.scatter(
            row["年化波动率"],
            row["年化收益"],
            s=100,
            color=colors.get(model, "gray"),
            label=model,
        )
        # 添加标签
        plt.text(row["年化波动率"] + 0.001, row["年化收益"] + 0.001, model, fontsize=10)

    # 设置图表属性
    plt.title("风险收益散点图", fontsize=14, fontweight="bold")
    plt.xlabel("年化波动率")
    plt.ylabel("年化收益")
    plt.grid(alpha=0.3, linestyle="--")

    # 保存图片
    save_path = os.path.join(output_folder, "风险收益散点图.png")
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"已保存图表：{save_path}")


def plot_portfolio_vs_bond(
    portfolio_returns_rp,
    portfolio_returns_c,
    asset_df,
    output_folder="rp_model_plots",
    portfolio_returns_rp_leverage=None,
    portfolio_returns_c_leverage=None,
):
    """
    绘制组合净值与10年期国债期货净值对比图

    参数：
        portfolio_returns_rp: 标准RP组合收益率
        portfolio_returns_c: 宽松RP组合收益率
        asset_df: 原始资产数据
        output_folder: 图片保存文件夹
        portfolio_returns_rp_leverage: 标准RP带杠杆组合收益率
        portfolio_returns_c_leverage: 宽松RP带杠杆组合收益率
    """
    import os
    import pandas as pd
    import matplotlib.pyplot as plt

    # 确保输出文件夹存在
    os.makedirs(output_folder, exist_ok=True)

    # 获取10年期国债期货数据
    ten_year_bond_col = "CFFEX10年期国债期货"
    if ten_year_bond_col in asset_df.columns:
        # 转换日期格式
        asset_df["date"] = pd.to_datetime(asset_df["date"])
        bond_data = asset_df[["date", ten_year_bond_col]].copy()
        bond_data = bond_data.set_index("date")

        # 计算10年期国债期货的收益率和累计收益
        bond_returns = bond_data.pct_change().dropna()

        # 使用配置中的起始日期
        plot_start_date = pd.Timestamp(CONFIG["plot_start_date"])

        # 对齐日期
        start_date = max(
            plot_start_date,
            portfolio_returns_rp.index.min(),
            portfolio_returns_c.index.min(),
            bond_returns.index.min(),
        )
        end_date = min(
            portfolio_returns_rp.index.max(),
            portfolio_returns_c.index.max(),
            bond_returns.index.max(),
        )

        # 筛选数据
        portfolio_rp_filtered = portfolio_returns_rp.loc[start_date:end_date]
        portfolio_c_filtered = portfolio_returns_c.loc[start_date:end_date]
        bond_returns_filtered = bond_returns.loc[start_date:end_date]

        # 筛选带杠杆收益数据（如果提供）
        has_leverage = (
            portfolio_returns_rp_leverage is not None
            and portfolio_returns_c_leverage is not None
        )
        if has_leverage:
            portfolio_rp_leverage_filtered = portfolio_returns_rp_leverage.loc[
                start_date:end_date
            ]
            portfolio_c_leverage_filtered = portfolio_returns_c_leverage.loc[
                start_date:end_date
            ]

        # 计算累计收益（确保第一天净值为1）
        cum_rp = (1 + portfolio_rp_filtered).cumprod()
        cum_rp.iloc[0] = 1  # 第一天净值设为1
        cum_c = (1 + portfolio_c_filtered).cumprod()
        cum_c.iloc[0] = 1  # 第一天净值设为1
        cum_bond = (1 + bond_returns_filtered).cumprod()
        cum_bond.iloc[0] = 1  # 第一天净值设为1

        # 计算带杠杆的累计收益
        if has_leverage:
            cum_rp_leverage = (1 + portfolio_rp_leverage_filtered).cumprod()
            cum_rp_leverage.iloc[0] = 1  # 第一天净值设为1
            cum_c_leverage = (1 + portfolio_c_leverage_filtered).cumprod()
            cum_c_leverage.iloc[0] = 1  # 第一天净值设为1

        # 调试信息
        print(
            f"组合RP累计收益长度: {len(cum_rp)}, 起始日期: {cum_rp.index.min()}, 结束日期: {cum_rp.index.max()}"
        )
        print(
            f"组合C累计收益长度: {len(cum_c)}, 起始日期: {cum_c.index.min()}, 结束日期: {cum_c.index.max()}"
        )
        if has_leverage:
            print(
                f"组合RP带杠杆累计收益长度: {len(cum_rp_leverage)}, 起始日期: {cum_rp_leverage.index.min()}, 结束日期: {cum_rp_leverage.index.max()}"
            )
            print(
                f"组合C带杠杆累计收益长度: {len(cum_c_leverage)}, 起始日期: {cum_c_leverage.index.min()}, 结束日期: {cum_c_leverage.index.max()}"
            )
        print(
            f"国债期货累计收益长度: {len(cum_bond)}, 起始日期: {cum_bond.index.min()}, 结束日期: {cum_bond.index.max()}"
        )

        # 绘制图表
        plt.figure(figsize=(14, 7))

        # 使用plot_date确保日期正确显示
        plt.plot_date(
            cum_rp.index, cum_rp.values, "-", label="标准RP组合（无杠杆）", linewidth=2
        )
        plt.plot_date(
            cum_c.index, cum_c.values, "-", label="宽松RP组合（无杠杆）", linewidth=2
        )

        # 添加带杠杆的曲线
        if has_leverage:
            plt.plot_date(
                cum_rp_leverage.index,
                cum_rp_leverage.values,
                "--",
                label="标准RP组合（带杠杆）",
                linewidth=2,
            )
            plt.plot_date(
                cum_c_leverage.index,
                cum_c_leverage.values,
                "--",
                label="宽松RP组合（带杠杆）",
                linewidth=2,
            )

        plt.plot_date(
            cum_bond.index, cum_bond.values, ":", label=ten_year_bond_col, linewidth=2
        )

        plt.title("组合净值与10年期国债期货净值对比", fontsize=14, fontweight="bold")
        plt.xlabel("日期")
        plt.ylabel("累计净值 (起始=1)")
        plt.legend(fontsize=11)

        # 设置X轴日期格式
        setup_date_axis(plt.gca(), start_date, end_date)

        plt.tight_layout()

        # 保存图片
        save_path = os.path.join(output_folder, "组合净值与10年期国债期货对比.png")
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"已保存图表：{save_path}")
    else:
        print(f"数据中没有找到{ten_year_bond_col}列")


def plot_model_weights_comparison(
    weights_df_rp, weights_df_c, output_folder="rp_model_plots"
):
    """
    绘制两个模型的持仓变化情况图

    参数：
        weights_df_rp: 标准RP权重DataFrame
        weights_df_c: 宽松RP权重DataFrame
        output_folder: 图片保存文件夹
    """
    import os
    import pandas as pd

    # 确保输出文件夹存在
    os.makedirs(output_folder, exist_ok=True)

    # 使用配置中的起始日期
    plot_start_date = pd.Timestamp(CONFIG["plot_start_date"])

    # 筛选有效权重（去除零值和NaN）
    weights_rp = (
        weights_df_rp[weights_df_rp.index >= plot_start_date]
        .copy()
        .clip(lower=0)
        .fillna(0)
    )
    weights_c = (
        weights_df_c[weights_df_c.index >= plot_start_date]
        .copy()
        .clip(lower=0)
        .fillna(0)
    )

    # 归一化权重
    weights_rp = weights_rp.div(weights_rp.sum(axis=1), axis=0).fillna(0)
    weights_c = weights_c.div(weights_c.sum(axis=1), axis=0).fillna(0)

    # 定义券商研报风格的颜色映射（深红、深蓝为主色）
    # 为权重高的资产（0-5信用票、国债期货等）设置深红和深蓝色
    asset_color_map = {
        "0-5中高信用票": "#B22222",  # 火砖红
        "CFFEX10年期国债期货": "#000080",  # 海军蓝
        "CFFEX2年期国债期货": "#FF8C00",  # 橙色
        "CFFEX30年期国债期货": "#9932CC",  # 紫色
    }

    # 其他资产使用高对比度颜色
    distinct_colors = [
        "#FF4500",
        "#228B22",
        "#FFD700",
        "#4169E1",
        "#DC143C",
        "#8B0000",
        "#00CED1",
        "#FF1493",
        "#ADFF2F",
        "#FFB6C1",
        "#20B2AA",
        "#DDA0DD",
        "#D2691E",
        "#F0E68C",
        "#8B4513",
        "#98FB98",
        "#BDB76B",
        "#FFDAB9",
        "#4682B4",
        "#A9A9A9",
    ]

    # 为每个资产分配颜色
    colors_rp = []
    for col in weights_rp.columns:
        if col in asset_color_map:
            colors_rp.append(asset_color_map[col])
        else:
            # 为其他资产从颜色列表中循环分配
            idx = len(colors_rp) % len(distinct_colors)
            colors_rp.append(distinct_colors[idx])

    # 绘制标准RP权重
    plt.figure(figsize=(14, 6))
    ax1 = plt.gca()
    weights_rp.plot.area(ax=ax1, stacked=True, linewidth=1, color=colors_rp)
    ax1.set_title("标准RP模型持仓变化", fontsize=14, fontweight="bold")
    ax1.set_xlabel("日期")
    ax1.set_ylabel("权重占比")
    ax1.legend(fontsize=10, bbox_to_anchor=(1.05, 1), loc="upper left")
    setup_date_axis(ax1, plot_start_date, weights_rp.index[-1])
    plt.tight_layout()
    save_path_rp = os.path.join(output_folder, "标准RP模型持仓变化.png")
    plt.savefig(save_path_rp, dpi=300, bbox_inches="tight")
    plt.close()

    # 为宽松RP模型分配颜色（使用相同的颜色映射逻辑）
    colors_c = []
    for col in weights_c.columns:
        if col in asset_color_map:
            colors_c.append(asset_color_map[col])
        else:
            # 为其他资产从颜色列表中循环分配
            idx = len(colors_c) % len(distinct_colors)
            colors_c.append(distinct_colors[idx])

    # 绘制宽松RP权重
    plt.figure(figsize=(14, 6))
    ax2 = plt.gca()
    weights_c.plot.area(ax=ax2, stacked=True, linewidth=1, color=colors_c)
    ax2.set_title("宽松RP模型持仓变化", fontsize=14, fontweight="bold")
    ax2.set_xlabel("日期")
    ax2.set_ylabel("权重占比")
    ax2.legend(fontsize=10, bbox_to_anchor=(1.05, 1), loc="upper left")
    setup_date_axis(ax2, plot_start_date, weights_c.index[-1])
    plt.tight_layout()
    save_path_c = os.path.join(output_folder, "宽松RP模型持仓变化.png")
    plt.savefig(save_path_c, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"已保存图表：{save_path_rp}, {save_path_c}")


def plot_asset_class_evolution(
    weights_df_rp, weights_df_c, output_folder="rp_model_plots"
):
    """
    绘制大类资产变化情况图
    大类资产分类：
        - 黄金：黄金ETF
        - 商品：有色ETF大成
        - 港股：恒生科技指数ETF, 恒生ETF
        - A股：沪深300ETF华泰柏瑞, 上证指数ETF, 中证1000ETF, 科创50ETF, 红利ETF
        - 债券：0-5中高信用票, CFFEX10年期国债期货, CFFEX2年期国债期货, CFFEX30年期国债期货

    参数：
        weights_df_rp: 标准RP权重DataFrame
        weights_df_c: 宽松RP权重DataFrame
        output_folder: 图片保存文件夹
    """
    import os
    import pandas as pd

    # 确保输出文件夹存在
    os.makedirs(output_folder, exist_ok=True)

    # 使用配置中的起始日期
    plot_start_date = pd.Timestamp(CONFIG["plot_start_date"])

    # 筛选指定日期范围内的数据
    weights_df_rp = weights_df_rp[weights_df_rp.index >= plot_start_date]
    weights_df_c = weights_df_c[weights_df_c.index >= plot_start_date]

    # 定义大类资产分类
    asset_classes = {
        "黄金": ["黄金ETF"],
        "商品": ["有色ETF大成"],
        "港股": ["恒生科技指数ETF", "恒生ETF"],
        "海外": ["标普500ETF", "纳指ETF", "日经225ETF"],
        "A股": [
            "沪深300ETF华泰柏瑞",
            "上证指数ETF",
            "中证1000ETF",
            "科创50ETF",
            "红利ETF",
        ],
        "债券": [
            "0-5中高信用票",
            "CFFEX10年期国债期货",
            "CFFEX2年期国债期货",
            "CFFEX30年期国债期货",
        ],
    }

    # 函数：将单模型权重转换为大类资产权重
    def convert_to_asset_class_weights(weights_df, asset_classes):
        asset_class_weights = pd.DataFrame(index=weights_df.index)

        for asset_class, assets in asset_classes.items():
            # 筛选存在的资产
            available_assets = [
                asset for asset in assets if asset in weights_df.columns
            ]
            if available_assets:
                asset_class_weights[asset_class] = weights_df[available_assets].sum(
                    axis=1
                )

        # 归一化
        asset_class_weights = asset_class_weights.div(
            asset_class_weights.sum(axis=1), axis=0
        ).fillna(0)
        return asset_class_weights

    # 转换两个模型的权重
    rp_asset_class = convert_to_asset_class_weights(weights_df_rp, asset_classes)
    c_asset_class = convert_to_asset_class_weights(weights_df_c, asset_classes)

    # 绘制两个子图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), sharex=True)

    # 标准RP大类资产权重
    rp_asset_class.plot.area(ax=ax1, stacked=True, linewidth=1)
    ax1.set_title("标准RP模型大类资产配置变化", fontsize=14, fontweight="bold")
    ax1.set_ylabel("权重占比")
    ax1.legend(fontsize=10, bbox_to_anchor=(1.05, 1), loc="upper left")
    setup_date_axis(ax1, plot_start_date, rp_asset_class.index[-1])

    # 宽松RP大类资产权重
    c_asset_class.plot.area(ax=ax2, stacked=True, linewidth=1)
    ax2.set_title("宽松RP模型大类资产配置变化", fontsize=14, fontweight="bold")
    ax2.set_xlabel("日期")
    ax2.set_ylabel("权重占比")
    ax2.legend(fontsize=10, bbox_to_anchor=(1.05, 1), loc="upper left")
    setup_date_axis(ax2, plot_start_date, c_asset_class.index[-1])

    plt.tight_layout()

    # 保存图片
    save_path = os.path.join(output_folder, "大类资产配置变化.png")
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"已保存图表：{save_path}")


CONFIG = {
    "lookback_weeks": 48,
    "trading_days_per_year": 243,  # 贴合A股实际交易日，提升年化指标准确性
    "plot_start_date": "2021-01-01",  # 图表显示起始日期
    # ---------- 模型核心参数（风险平价/宽松RP） ----------
    "lambda_pen": 1.9,  # 惩罚系数（λ<1，论文推荐范围，平衡收益与分散）
    "m": 1.9,  # 收益增强乘数（小幅增强，兼顾稳健性）
    "optim_tol": 1e-6,  # 优化器收敛精度
    "optim_maxiter": 2000,  # 合理迭代次数，提升优化速度
    # ---------- 资产配置约束参数 ----------
    "asset_weight_bounds": (0.00, 1.0),  # 单资产权重上下限（长仓约束）
    "max_single_asset_weight": 1,  # 单资产权重上限（限制过度集中）
    "bond_keywords": ["国债", "信用票", "美债"],  # 债券动态识别关键词
    "bond_leverage_upper": 1.4,  # 债券杠杆上限（符合公募债基最大杠杆1.4倍）
    "risk_free_rate": 0.0182,  # 无风险利率（计算夏普比率用）
    # ---------- 可视化配置参数 ----------
    "plot_start_date": "2021-01-01",  # 图表起始展示日期
}

asset_df_v1 = asset_df[
    [
        "date",
        "黄金ETF",
        "有色ETF大成",
        "恒生科技指数ETF",
        "恒生ETF",
        "沪深300ETF华泰柏瑞",
        "上证指数ETF",
        "中证1000ETF",
        "科创50ETF",
        "红利ETF",
        "0-5中高信用票",
        "CFFEX10年期国债期货",
        "CFFEX2年期国债期货",
        "CFFEX30年期国债期货",
    ]
]
asset_df_v1 = asset_df_v1[asset_df_v1["date"] >= "2020-01-01"]
asset_df_v1.to_csv(
    _resolve_path("rp_model_input.csv"), encoding="utf-8-sig", index=False
)


def run_version(version, model_type, asset_columns, output_folder):
    """
    运行指定版本的回测

    参数：
        version: 版本名称，如 "V1", "V2", "V3"
        model_type: 模型类型，"standard" 或 "relaxed"
        asset_columns: 资产列列表
        output_folder: 输出文件夹路径
    """
    import os
    import pandas as pd

    # 确保asset_df在全局作用域中定义
    global asset_df

    print(f"\n===================== 运行版本 {version} =====================")
    print(f"模型类型: {'标准风险平价' if model_type == 'standard' else '宽松风险平价'}")
    print(f"资产数量: {len(asset_columns) - 1} (包含date列)")
    print(f"输出文件夹: {output_folder}")

    output_folder = str(_resolve_path(output_folder))

    # 创建输出文件夹
    os.makedirs(output_folder, exist_ok=True)
    print(f"输出文件夹已创建: {output_folder}")

    # 准备数据
    print(f"正在准备数据...")
    asset_df_version = asset_df[asset_columns].copy()
    asset_df_version = asset_df_version[asset_df_version["date"] >= "2018-01-01"]
    print(f"数据准备完成，样本数量: {len(asset_df_version)}")

    # 保存为临时文件
    temp_file = _resolve_path(f"rp_model_input_{version}.csv")
    asset_df_version.to_csv(temp_file, encoding="utf-8-sig", index=False)
    print(f"临时数据文件已保存: {temp_file}")

    # 运行回测
    print(f"正在运行回测...")
    main(file_path=str(temp_file), model_type=model_type, output_folder=output_folder)

    # 清理临时文件
    if temp_file.exists():
        temp_file.unlink()
        print(f"临时数据文件已清理: {temp_file}")

    print(f"版本 {version} 回测完成！")


if __name__ == "__main__":
    """月度更新主入口：支持新Pipeline + 原有逻辑兼容"""
    import argparse
    import sys
    
    # 检查是否有新参数，如果没有或者只有原有参数，则运行原有逻辑
    # 如果有 --mode 参数，则调用新pipeline
    if "--mode" in sys.argv:
        from scripts.run_rrp_pipeline import main as run_pipeline
        run_pipeline()
        sys.exit(0)

    # 原有逻辑...
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="资产配置月度更新脚本")
    parser.add_argument(
        "--update-wind",
        action="store_true",
        help="是否更新Wind数据"
    )
    parser.add_argument(
        "--run-backtest",
        action="store_true",
        help="是否运行回测分析"
    )
    parser.add_argument(
        "--wind-dir",
        type=str,
        default=None,
        help="Wind数据文件目录"
    )
    
    args = parser.parse_args()
    
    # 如果没有指定任何参数，默认运行回测（保持兼容性）
    if not args.update_wind and not args.run_backtest:
        args.run_backtest = True
    
    print("=" * 70)
    print(" "*20 + "资产配置月度更新脚本")
    print("=" * 70)
    
    # 步骤1: Wind数据更新
    if args.update_wind:
        print("\n" + "=" * 70)
        print("步骤1: 更新Wind数据")
        print("=" * 70)
        
        if not WIND_AVAILABLE:
            print("错误: WindPy不可用，跳过数据更新")
        else:
            wind_dir = args.wind_dir if args.wind_dir else str(BASE_DIR)
            latest_file = update_data_from_wind(file_dir=wind_dir)
            
            if latest_file:
                print(f"\n✓ Wind数据更新成功: {latest_file}")
            else:
                print("\n✗ Wind数据更新失败")
    
    # 步骤2: 运行风险平价分析
    if args.run_backtest:
        print("\n" + "=" * 70)
        print("步骤2: 风险平价回测分析")
        print("=" * 70)
        
        # 定义三个版本的资产列表
        asset_columns_v1 = [
            "date",
            "黄金ETF",
            "有色ETF大成",
            "恒生科技指数ETF",
            "恒生ETF",
            "沪深300ETF华泰柏瑞",
            "上证指数ETF",
            "中证1000ETF",
            "科创50ETF",
            "红利ETF",
            "0-5中高信用票",
            "CFFEX10年期国债期货",
            "CFFEX2年期国债期货",
            "CFFEX30年期国债期货",
        ]

        asset_columns_v3 = [
            "date",
            "黄金ETF",
            "有色ETF大成",
            "恒生科技指数ETF",
            "恒生ETF",
            "沪深300ETF华泰柏瑞",
            "上证指数ETF",
            "中证1000ETF",
            "科创50ETF",
            "红利ETF",
            "纳指ETF",
            "标普500ETF",
            "日经225ETF",
            "0-5中高信用票",
            "CFFEX10年期国债期货",
            "CFFEX2年期国债期货",
            "CFFEX30年期国债期货",
            "CBOT10年美债连续",
        ]

        base_output_folder = "rp_model_plots"

        # 运行V1：标准风险平价模型，使用资产列表1
        output_folder_v1 = os.path.join(base_output_folder, "V1")
        run_version("V1", "standard", asset_columns_v1, output_folder_v1)

        # 运行V2：宽松风险平价模型，使用资产列表1
        output_folder_v2 = os.path.join(base_output_folder, "V2")
        run_version("V2", "relaxed", asset_columns_v1, output_folder_v2)

        # 运行V3：宽松风险平价模型，使用资产列表3
        output_folder_v3 = os.path.join(base_output_folder, "V3")
        run_version("V3", "relaxed", asset_columns_v3, output_folder_v3)

        print("\n" + "=" * 70)
        print(" "*20 + "所有版本回测完成")
        print("=" * 70)
    
    print("\n✓ 月度更新流程完成！")
