# ETF 资产池变更完整操作手册

本文档记录从"修改ETF资产池"到"论文PDF编译并合并到main"的完整操作流程。
每次变更ETF时，按本文档顺序执行，不得跳步。

---

## 快速参考：完整命令序列

```powershell
# 0. 进入项目目录
cd "D:\Github Repository\Relaxed-Risk-Parity-Research"

# 1. 修改 src/asset_universe.py（手动编辑，见下文说明）

# 2. 拉取数据
$env:TUSHARE_TOKEN="ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53"
python scripts/update_etf_data.py --provider tushare --start-date 20100101

# 3. 运行全流程脚本（顺序不可颠倒）
python scripts/run_convex_adaptive_rrp.py
python scripts/run_hrp_comparison.py
python scripts/run_asset_descriptive_statistics.py
python scripts/run_sharpe_diff_tests.py
python scripts/augment_supplementary_csvs.py
python scripts/run_vol_aligned_comparison.py
python scripts/generate_thesis_numbers.py

# 4. 更新文档（手动，见下文）

# 5. 编译PDF
cd report/thesis_latex
latexmk -xelatex -interaction=nonstopmode main.tex
latexmk -xelatex -interaction=nonstopmode main.tex
latexmk -xelatex -interaction=nonstopmode main.tex
cd ../..

# 6. Git提交合并
git add -A
git commit -m "feat: ETF universe change - <描述变更内容>"
git push origin main
```

---

## Step 0：理解资产池约束

在决定替换哪支ETF之前，必须检查以下几点：

### 数据长度要求

评估窗口从 **2019-01-01** 开始（全30支ETF均可投资的最早时间点）。  
新增ETF的上市日期必须在 **2018年年底之前**，否则在评估窗口开始时仍未上市，会被点在时过滤器排除，导致该ETF在绝大多数回测期间无法参与优化，降低分散化效果。

```
ETF上市日期 < 2018-12-31  →  可以有效参与2019年起的回测
ETF上市日期 > 2019-01-01  →  早期被排除，实际作用大打折扣
ETF上市日期 > 2022-01-01  →  极短历史，几乎不参与回测，强烈不建议
```

### 相关性检查

替换前应检查新ETF与同类别现有ETF的相关性。相关性 > 0.90 意味着几乎没有额外的分散化价值。

```python
# 快速相关性检查（在Python shell中运行）
import pandas as pd
prices = pd.read_csv("data/processed/etf_prices_updated.csv", index_col=0, parse_dates=True)
print(prices[["新ETF_ticker", "现有同类ETF_ticker"]].corr())
```

---

## Step 1：修改 `src/asset_universe.py`

这是 **唯一需要手动编辑的配置文件**。所有其他文件均由脚本自动生成。

### 文件位置

```
src/asset_universe.py
```

### AssetMapping 结构

```python
AssetMapping(
    name="半导体设备ETF",        # 中文名（论文/README中显示的名称）
    display_name="半导体设备ETF", # 显示名（通常与name相同）
    ticker="159516.SZ",          # Tushare格式：纯数字+.SZ/.SH
    asset_class="china tech equity",  # 资产类别（见下方允许值）
    description="Semiconductor equipment ETF..."  # 英文说明
)
```

### Tushare Ticker格式

Tushare使用 `数字代码.交易所后缀` 格式：
- 上交所（沪市）：`.SH`（如 `512480.SH`）
- 深交所（深市）：`.SZ`（如 `159516.SZ`）
- 特殊：161226（白银LOF）在Tushare中用 `161226.SZ`

**注意：**`data/MANIFEST.json` 中存储的ticker格式可能不同（无后缀），但 `asset_universe.py` 必须使用带后缀格式。

### 允许的 asset_class 值

```
government bond        # 国债
credit bond            # 信用债
convertible bond       # 可转债
money market           # 货币市场
china equity           # A股宽基
china equity dividend  # A股红利
china tech equity      # 中国科技
china advanced manufacturing  # 先进制造
china new energy       # 新能源
china finance          # 中国金融
china defense          # 中国军工
china consumer         # 中国消费
hong kong equity       # 港股
global equity          # 全球股票
commodity              # 大宗商品
commodity equity       # 大宗商品权益
```

### 替换示例

```python
# 删除旧条目，添加新条目
# 替换前：
AssetMapping("消费电子ETF", "消费电子ETF", "159839.SZ", "china tech equity",
             "Consumer electronics ETF.")

# 替换后：
AssetMapping("半导体设备ETF", "半导体设备ETF", "159516.SZ", "china tech equity",
             "Semiconductor equipment ETF targeting upstream chip manufacturing supply chain.")
```

### 验证

修改后运行以下命令确认恰好30条：

```python
python -c "from src.asset_universe import ASSET_UNIVERSE; print(len(ASSET_UNIVERSE.assets), 'assets')"
```

---

## Step 2：拉取数据

```powershell
$env:TUSHARE_TOKEN="ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53"
python scripts/update_etf_data.py --provider tushare --start-date 20100101
```

说明：
- `--start-date 20100101`：从2010年开始拉，确保获取每支ETF的完整可用历史
- 脚本会自动处理缺失数据（缺失率高的品种会被标记但仍保留）
- 输出文件：`data/processed/etf_prices_updated.csv`
- 运行时间约5-15分钟（取决于网络和Tushare频率限制）

验证：

```python
import pandas as pd
prices = pd.read_csv("data/processed/etf_prices_updated.csv", index_col=0, parse_dates=True)
print(f"日期范围: {prices.index.min()} 至 {prices.index.max()}")
print(f"ETF数量: {prices.shape[1]}")
print(prices.count().sort_values())  # 查看各ETF数据条数，排查短历史问题
```

---

## Step 3：运行全流程脚本（顺序不可颠倒）

以下7个脚本必须按顺序执行，每个脚本的输出是下一个脚本的输入。

### 3.1 主模型优化

```powershell
python scripts/run_convex_adaptive_rrp.py
```

- 耗时：20-60分钟（取决于CPU）
- 输出：`results/tables/convex_adaptive_performance_summary.csv`（主结果文件）
- 同时输出：`results/figures/convex_adaptive_*.png`（NAV/回撤/换手率/CVaR图）
- 如果卡死：检查Python进程是否僵尸，`taskkill /F /IM python.exe`后重跑

### 3.2 HRP/HERC对比基准

```powershell
python scripts/run_hrp_comparison.py
```

- 耗时：5-15分钟
- 输出：`results/tables/hrp_comparison.csv`
- 包含：Global RRP、Defensive RRP、HRP、HERC、Equal Weight全部对比结果

### 3.3 ETF描述性统计

```powershell
python scripts/run_asset_descriptive_statistics.py
```

- 耗时：1-3分钟
- 输出：`results/tables/asset_descriptive_statistics.csv`
- 包含每支ETF的年化收益、波动率、最大回撤、数据条数

### 3.4 Sharpe差异显著性检验

```powershell
python scripts/run_sharpe_diff_tests.py
```

- 耗时：1分钟
- 输出：`results/tables/sharpe_difference_tests.csv`
- 包含各模型两两Sharpe差值的bootstrap置信区间和p值

### 3.5 补充性CSV（交易成本盈亏平衡等）

```powershell
python scripts/augment_supplementary_csvs.py
```

- 耗时：1-2分钟
- 输出：`results/tables/transaction_cost_breakeven.csv` 等
- 此步骤跳过会导致LaTeX编译报错（`\costBreakevenImprovedVsGlobal` undefined）

### 3.6 波动率对齐对比

```powershell
python scripts/run_vol_aligned_comparison.py
```

- 耗时：1-2分钟
- 输出：`results/tables/vol_aligned_comparison.csv`
- 此步骤跳过会导致LaTeX编译报错（`\improvedVolAlignedHrpSharpe` undefined）

### 3.7 生成LaTeX宏文件

```powershell
python scripts/generate_thesis_numbers.py
```

- 耗时：<1分钟
- 输出：`report/thesis_latex/generated_numbers.tex`
- 从以上所有CSV读取数字，生成约160个LaTeX `\newcommand` 宏
- **重要**：此文件由脚本自动覆盖，不要手动编辑

---

## Step 4：更新文档文字

以下文件需要手动更新。数字部分由LaTeX宏自动填充，需要手动更新的只有**文字描述**（ETF名称、类别说明等）。

### 4.1 `src/asset_universe.py` 附近文档无需额外修改

### 4.2 `report/thesis_latex/main.tex`

需要更新的位置（搜索关键词定位）：

| 位置 | 搜索关键词 | 需要更新的内容 |
|------|-----------|--------------|
| 中文摘要（~100行） | `30只ETF` | ETF类别描述文字 |
| 英文摘要（~115行） | `30 ETFs` | ETF类别描述文字 |
| 第4章ETF池表格（~344行） | `tab:etf_pool` | 修改3行的ETF名称/Ticker/类别 |
| 第4章表格后叙述（~375行） | `china_tech_equity` | 更新科技类ETF名称列表 |
| 第4章资产统计表（~420行） | 各ETF中文名 | 替换被删除ETF的统计行 |
| 第4章资产统计叙述（~465行） | 各ETF中文名 | 更新文字描述 |

**摘要文字模板（中文）**：
```
本文构建了一个包含30只ETF的全球多资产投资组合，覆盖中国股票（宽基、科技、行业）、债券、港股、全球股票及大宗商品等八大资产类别。
```

**摘要文字模板（英文）**：
```
The portfolio spans 30 ETFs across eight asset categories: Chinese broad-market equity, technology equity (including semiconductor, AI, robotics, new energy, semiconductor equipment, communications, and cloud computing), sector equity, bonds, Hong Kong equity, global equity, and commodities.
```

### 4.3 `AGENTS.md`

更新 "ETF Asset Pool" 部分的表格，将修改的3行替换为新ETF。

### 4.4 `README.md`

- 如果有ETF清单表格，同步更新
- 绩效看板数字由脚本自动生成，手动检查无明显异常即可

---

## Step 5：编译PDF

```powershell
cd report/thesis_latex
latexmk -xelatex -interaction=nonstopmode main.tex
```

或者手动三遍：
```powershell
xelatex main.tex
xelatex main.tex
xelatex main.tex
```

### 常见编译错误

| 错误信息 | 原因 | 解决方法 |
|---------|------|---------|
| `Undefined control sequence \costBreakevenImprovedVsGlobal` | Step 3.5 未运行 | 运行 `augment_supplementary_csvs.py` |
| `Undefined control sequence \improvedVolAlignedHrpSharpe` | Step 3.6 未运行 | 运行 `run_vol_aligned_comparison.py` |
| `Undefined control sequence \improvedVsGlobalDiff` | Step 3.4 未运行 | 运行 `run_sharpe_diff_tests.py` |
| `File not found: generated_numbers.tex` | Step 3.7 未运行 | 运行 `generate_thesis_numbers.py` |
| `Package inputenc Error` | 文件编码问题 | 确保文件UTF-8无BOM保存 |

编译成功标志：无 `Error` 输出，生成 `main.pdf`。

---

## Step 6：Git提交

```powershell
# 确认在项目根目录
cd "D:\Github Repository\Relaxed-Risk-Parity-Research"

# 查看变更
git status
git diff src/asset_universe.py

# 提交（选择性添加文件，避免提交临时文件）
git add src/asset_universe.py
git add data/processed/etf_prices_updated.csv
git add results/tables/
git add results/figures/
git add report/thesis_latex/generated_numbers.tex
git add report/thesis_latex/main.tex
git add report/thesis_latex/main.pdf
git add README.md
git add AGENTS.md

git commit -m "feat: ETF universe - <简要描述变更，如 replace 半导体设备 with X>"

git push origin main
```

---

## 诊断：如何判断结果是否合理

运行完成后，检查以下指标：

```python
import pandas as pd
df = pd.read_csv("results/tables/convex_adaptive_performance_summary.csv")
print(df[["model", "net_annual_return", "sharpe_ratio", "max_drawdown", "avg_monthly_turnover"]])
```

### 合理范围参考（基于2019-2026评估窗口）

| 模型 | Sharpe合理范围 | 月换手率合理范围 |
|------|-------------|---------------|
| Improved Convex Adaptive Global RRP | 1.2 - 1.6 | 2% - 6% |
| Convex Adaptive Global RRP | 0.8 - 1.2 | 0.5% - 3% |
| Global RRP | 0.5 - 0.9 | 15% - 25% |
| Equal Weight | 0.7 - 1.0 | 1% - 2% |

### 结果变差的常见原因

1. **新ETF历史太短**：检查 `asset_descriptive_statistics.csv` 中新ETF的 `available_observations`，若 < 1000条（上市晚于2019年），该ETF在评估期前段会被点在时过滤器排除，等效于分散化资产减少。

2. **相关性过高**：新ETF与同板块ETF相关性 > 0.90，几乎不提供额外分散化，优化器无法利用。

3. **极端波动率**：新ETF波动率 > 35% 年化，CVaR约束会将其权重压制到接近零，等于没引入新资产。

4. **数据质量问题**：Tushare返回的数据有缺口，`missing_ratio` 过高（> 0.70）的ETF实际上只有少量有效数据。

---

## 附：当前资产池（2026-05-15版本）

| 类别 | ETF | Ticker | 上市日期 | 备注 |
|------|-----|--------|---------|------|
| government bond | 国债ETF | 511010.SH | 2013-03 | 充足 |
| credit bond | 信用债ETF | 511030.SH | 2019-03 | 充足 |
| convertible bond | 可转债ETF | 511380.SH | 2020-04 | 较短 |
| money market | 日利ETF | 511880.SH | 2013-08 | 充足 |
| china equity | 沪深300ETF | 510300.SH | 2012-05 | 充足 |
| china equity | 中证500ETF | 510500.SH | 2013-03 | 充足 |
| china equity | 中证1000ETF | 512100.SH | 2014-01 | 充足 |
| china equity | 创业板ETF | 159915.SZ | 2011-09 | 充足 |
| china equity dividend | 红利ETF | 510880.SH | 2006-11 | 充足 |
| china tech equity | 半导体ETF | 512480.SH | 2019-06 | 可用 |
| china tech equity | 人工智能ETF | 159819.SZ | 2020-09 | 较短 |
| china advanced manufacturing | 机器人ETF | 562500.SH | 2021-12 | 短 |
| china new energy | 新能源ETF | 516160.SH | 2021-02 | 短 |
| china tech equity | **半导体设备ETF** | **159516.SZ** | **2023-07** | ⚠️极短 |
| china tech equity | 通信ETF | 159695.SZ | 2023-05 | ⚠️极短 |
| china tech equity | 云计算ETF | 516980.SH | 2021-06 | 短 |
| china finance | 证券ETF | 512880.SH | 2013-05 | 充足 |
| china defense | 军工ETF | 512660.SH | 2013-05 | 充足 |
| china consumer | 消费ETF | 159928.SZ | 2009-02 | 充足 |
| hong kong equity | 恒生ETF | 159920.SZ | 2012-05 | 充足 |
| commodity | **白银LOF** | **161226.SZ** | 2014-12 | 充足 |
| global equity | 纳指ETF | 159941.SZ | 2013-05 | 充足 |
| global equity | 标普500ETF | 513500.SH | 2013-07 | 充足 |
| global equity | 日经225ETF | 513880.SH | 2019-06 | 可用 |
| global equity | 欧洲ETF | 513030.SH | 2015-09 | 充足 |
| commodity | 黄金ETF | 518880.SH | 2013-08 | 充足 |
| commodity equity | 有色ETF | 159980.SZ | 2019-12 | 可用 |
| commodity | 豆粕ETF | 159985.SZ | 2019-12 | 可用 |
| commodity | 煤炭ETF | 515220.SH | 2020-03 | 较短 |
| commodity | 原油ETF | 162411.SZ | 2004-06 | 充足 |

**⚠️ 注意**：标记为"极短"的ETF（半导体设备、通信）在2019-2026评估期的前半段不参与组合优化，建议下次修改时优先考虑替换这两个品种。

---

## 关于可改进的方向

如果希望进一步提升 Improved Convex Adaptive Global RRP 的 Sharpe：

1. **替换半导体设备ETF（159516.SZ）**：该ETF仅668条数据（2023-07上市），在评估期前4.5年完全缺席。可考虑替换为：
   - 半导体ETF（512480.SH）— 但已在资产池中
   - 芯片ETF (159995.SZ) — 需确认与现有半导体ETF相关性
   - 电子ETF (159864.SZ 或 516600.SH) — 起始日期需查验

2. **替换通信ETF（159695.SZ）**：同样2023-05上市，数据极短。

3. **调整超参数**：修改 `scripts/run_convex_adaptive_rrp.py` 中的候选参数网格（lookback、max_weight、turnover_cap、cvar_beta等），重跑网格搜索。

---

*最后更新：2026-05-15*  
*对应 git commit: ETF universe - replace 消费电子/恒生科技/科创50*
