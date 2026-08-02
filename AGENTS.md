# AGENTS.md

面向 AI 编程助手的项目协作规范。本文件描述 EMT 量化策略集合的约定，帮助 AI 生成符合项目风格的代码。

## 项目概览

- 基于 **掘金量化（gm.api）** 的 A 股量化策略集合，运行依赖本地**掘金终端**提供行情与交易通道。
- `projects/` 下每个子目录是一个**独立策略**，入口统一为 `main.py`，可单独回测运行。
- 现有策略：`DK`（DK 多空指标择时）、`EnhancedIndex`（指数增强）、`MovLine`（双均线）、`Small-cap`（小市值）。

## 运行与调试

- 运行前需启动并登录掘金终端。
- 进入策略目录后执行 `python main.py`（Python 3.11）。
- 依赖：`gm`、`numpy`、`pandas`。
- `gmcache/` 为 SDK 自动生成的缓存，**不要手动修改或提交无关变更**。

## 代码约定

- 文件首行保留 `# coding=utf-8`，并保留 `from __future__ import ...` 兼容导入。
- 掘金 API 采用官方模板要求的通配导入：`from gm.api import *`，不要改为具名导入。
- 遵循掘金策略生命周期回调命名：`init`、`on_bar`、`algo`（定时任务）、`on_order_status`、`on_error`、`on_market_data_connected` / `on_market_data_disconnected`、`on_backtest_finished`。
- 策略参数集中在 `init(context)` 中通过 `context.xxx` 定义，便于统一调参。
- 缩进使用 4 空格；注释与打印信息使用中文，保持与现有风格一致。
- 下单统一使用 `order_target_percent(...)` 目标仓位方式；A 股 / ETF 不做空，仅使用 `PositionSide_Long`。

## 安全与密钥

- **严禁硬编码 token**。token 一律通过环境变量 `GM_TOKEN` 读取：

  ```python
  token = os.getenv('GM_TOKEN')
  if not token:
      raise RuntimeError('请先设置环境变量 GM_TOKEN')
  ```

- 若发现历史文件中存在硬编码 token（如 `EnhancedIndex/main.py`），应改为环境变量读取，切勿在提交中新增明文密钥。
- 不要在代码、文档或提交信息中泄露真实 token、账户、资金等敏感信息。

## 回测参数

- 回测配置集中在 `main.py` 的 `run(...)` 调用中：`backtest_start_time`、`backtest_end_time`、`backtest_initial_cash`、`backtest_commission_ratio`、`backtest_slippage_ratio`、`backtest_match_mode` 等。
- 修改回测区间/资金/费率时只改 `run(...)` 参数，不要散落到策略逻辑内。
- `strategy_id` 由掘金系统生成，属各策略固有标识，改动需谨慎。

## 边界与健壮性

- 数据回调中先判空（`if not bars: return`）、校验标的、处理数据不足与除零（如区间为 0、停牌无数据返回 `None`）。
- 下单前用 `get_position()` 核对实际持仓，避免状态机与真实持仓不一致。
- 保持行情断连处理逻辑：断连时暂停信号处理，重连后恢复。

## 修改规范

- 优先做**最小化、针对性**的修改，避免大范围重写既有策略文件。
- 新增策略时沿用 `projects/<Name>/main.py` 结构；如有原理说明，放同目录 Markdown（参考 `projects/DK/DK.md`）。
- 涉及策略行为变更时，同步更新对应说明文档与 `README.md` 策略一览表。

## 免责声明

所有策略均为示例，仅供研究，不构成投资建议，未经验证请勿实盘。
