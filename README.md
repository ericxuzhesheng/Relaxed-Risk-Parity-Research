# Relaxed Risk Parity Research

### 宽松风险平价研究 | From Local Adaptation to Global Asset Allocation

<p align="center">
  <a href="#简体中文">
    <img src="https://img.shields.io/badge/LANGUAGE-中文-E74C3C?style=for-the-badge&labelColor=4B4B4B" alt="Language Chinese" />
  </a>
  <a href="#english">
    <img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2D77D1?style=for-the-badge&labelColor=4B4B4B" alt="Language English" />
  </a>
</p>

---

<a id="简体中文"></a>

## 简体中文

### 当前语言：中文 | [切换到英文](#english)

# 宽松风险平价研究

### 从本土适配到全球资产配置

## 📌 项目概览

本项目在低利率环境下对传统风险平价（RP）框架进行改进，提出宽松风险平价（RRP）模型。

核心目标是解决标准 RP 的关键局限：

> 低波动，但低收益

从而构建更灵活、更稳健、且可扩展至全球市场的资产配置策略。

本仓库包含：

- 📊 模型构建（RRP 框架）
- 📈 回测结果（V1 vs V2 vs V3）
- 🌍 全球资产配置扩展
- ⚙️ 含约束的工程化实现（杠杆、目标收益等）

## 🧠 研究动机

传统风险平价常见问题包括：

- 对低收益债券配置过高
- 牛市中的收益弹性不足
- 等风险贡献（ERC）硬约束过强

在低利率阶段，标准 RP 往往容易退化为类债券组合。

## 🚀 核心创新：RRP

RRP 不再强制严格满足：

$$
RC_i = RC_j
$$

而是引入：

- ✅ 松弛变量
- ✅ 惩罚项（λ）
- ✅ 动态收益约束

核心思想：

> 硬约束 -> 软惩罚优化

从而允许在完全等风险贡献附近可控偏离，提升分散化与收益之间的权衡能力。

## 🧩 模型结构

目标函数：最小化风险贡献离散程度。

$$
\min (\psi - \gamma)
$$

约束包括：

- 风险贡献下界约束
- 组合方差约束
- 松弛约束
- 目标收益约束

最终可转化为一个多约束非线性优化问题。

## ⚙️ 工程化增强

### 1. 债券杠杆模块

- 债券杠杆上限：1.4x
- 释放 20%–30% 资金给权益资产

### 2. 动态目标收益

$$
R_{target} = 1.9 \times R_{base}
$$

- 随市场状态自适应
- 避免固定目标收益假设不现实

### 3. 惩罚系数（λ）

- 控制偏离风险平价的程度
- 在 GMV（最小方差）与 ERC（风险平价）之间平衡

## 📊 策略对比

| 策略 | 说明                     |
| ---- | ------------------------ |
| V1   | 标准风险平价             |
| V2   | 放松风险平价（本土资产） |
| V3   | 放松风险平价 + 全球资产  |

### 🔍 核心回测结果

- V1 收益率：2.99%
- V2 收益率：5.18%
- V2 夏普：3.33

RRP 在风险调整后收益上有显著提升。

## 🌍 全球扩展（V3）

新增全球资产：

- S&P 500
- Nasdaq
- Nikkei 225
- US Treasuries

优势：

- 更低换手率
- 更强分散化
- 更低系统性风险

月度换手率可降至约 7.26%。

## 📂 仓库结构

```text
RRP.py
backtest/
  V1/
  V2/
  V3/
data/
report/
```

## ⚠️ 风险提示

- 模型风险与回测偏差
- 市场风格切换风险
- 交易执行与流动性风险

## 📄 许可证

本项目采用 MIT 许可证，详情见 [LICENSE](LICENSE)。

---

<a id="english"></a>

## English

### Current Language: English | [切换到中文](#简体中文)

# Relaxed Risk Parity Research

### From Local Adaptation to Global Asset Allocation

## 📌 Project Overview

This project improves the traditional Risk Parity (RP) framework in a low-interest-rate environment by introducing a Relaxed Risk Parity (RRP) model.

The core objective is to solve the key limitation of standard RP:

> low volatility but low return

and build a more flexible, robust, and globally applicable asset allocation strategy.

This repository includes:

- 📊 Model construction (RRP framework)
- 📈 Backtesting results (V1 vs V2 vs V3)
- 🌍 Global asset allocation extension
- ⚙️ Practical implementation with constraints (leverage, return target, etc.)

## 🧠 Motivation

Traditional Risk Parity often suffers from:

- Over-allocation to low-yield bonds
- Weak return elasticity in bull markets
- Hard constraint of equal risk contribution (ERC)

In low-rate regimes, standard RP can drift toward a bond-like portfolio.

## 🚀 Key Innovation: Relaxed Risk Parity (RRP)

Instead of enforcing strict equal risk contribution:

$$
RC_i = RC_j
$$

RRP introduces:

- ✅ Relaxation variables
- ✅ Penalty term (λ)
- ✅ Dynamic return constraint

Core idea:

> Hard constraint -> Soft-penalty optimization

This allows controlled deviation from perfect risk parity and a better trade-off between diversification and return.

## 🧩 Model Structure

Objective: minimize the dispersion of risk contribution.

$$
\min (\psi - \gamma)
$$

Subject to:

- Risk contribution lower bound
- Portfolio variance constraint
- Relaxation constraint
- Target return constraint

The problem becomes a multi-constraint nonlinear optimization problem.

## ⚙️ Practical Enhancements

### 1. Bond Leverage Module

- Bond leverage cap: 1.4x
- Releases 20%–30% capital to equities

### 2. Dynamic Return Target

$$
R_{target} = 1.9 \times R_{base}
$$

- Adaptive to market regime
- Avoids unrealistic fixed-return assumptions

### 3. Penalty Coefficient (λ)

- Controls deviation from risk parity
- Balances between GMV (minimum variance) and ERC (risk parity)

## 📊 Strategy Comparison

| Strategy | Description                        |
| -------- | ---------------------------------- |
| V1       | Standard Risk Parity               |
| V2       | Relaxed Risk Parity (Local assets) |
| V3       | Relaxed RP + Global assets         |

### 🔍 Key Backtest Results

- V1 Return: 2.99%
- V2 Return: 5.18%
- V2 Sharpe: 3.33

RRP shows a significant improvement in risk-adjusted return.

## 🌍 Global Extension (V3)

Added global assets include:

- S&P 500
- Nasdaq
- Nikkei 225
- US Treasuries

Benefits:

- Lower turnover
- Better diversification
- Reduced systemic risk

Monthly turnover drops to around 7.26%.

## 📂 Repository Structure

```text
RRP.py
backtest/
  V1/
  V2/
  V3/
data/
report/
```

## ⚠️ Risk Disclaimer

- Model risk and backtest bias
- Market regime shifts
- Execution and liquidity risks

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
