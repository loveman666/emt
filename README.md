# EMT — 掘金量化策略集合

基于 **掘金量化（gm.api / 掘金终端）** 的 A 股量化交易策略集合，涵盖择时、指数增强、双均线、小市值等多类策略。每个策略均为独立、可直接回测运行的 `main.py`。

## 项目结构

```
emt/
├── projects/
│   ├── DK/                # DK 多空指标择时策略（半导体 ETF）
│   │   ├── main.py
│   │   └── DK.md          # DK 指标原理与实现说明
│   ├── EnhancedIndex/     # 沪深300 指数增强策略
│   │   └── main.py
│   ├── MovLine/           # 20/60 双均线择时策略（半导体 ETF）
│   │   └── main.py
│   └── Small-cap/         # 全 A 小市值策略
│       ├── main.py
│       └── pyrightconfig.json
├── gmcache/               # 掘金 SDK 本地缓存（自动生成）
├── AGENTS.md              # AI 助手协作规范
└── README.md
```

> `gmcache/` 为掘金 SDK 运行时自动生成的缓存目录，无需手动维护。

## 策略一览

| 策略 | 目录 | 标的 | 周期 | 核心思路 |
|------|------|------|------|----------|
| DK 多空指标 | `projects/DK` | 半导体 ETF（`SHSE.512480`） | 5 分钟 | 基于东财 DK 指标近似公式，RSV 两次 SMA 平滑得多空线，状态机翻转 + 高低位阈值给出唯一买卖点 |
| 指数增强 | `projects/EnhancedIndex` | 沪深300 成份股（权重 > 0.35%） | 日频 | 以 0.8 为基准权重跟踪，按连涨/连跌 5 日区分强弱势股，动态调至 1.0 / 0.6 |
| 双均线 | `projects/MovLine` | 半导体 ETF（`SHSE.512480`） | 5 分钟 | 20/60 均线金叉建仓（95%）、死叉清仓，仅多仓 |
| 小市值 | `projects/Small-cap` | 全 A 市场 | 日频（月初调仓） | 等权买入市值最小的前 N 只股票（剔除停牌/ST/次新股） |

各策略详细原理见对应目录下的说明文档（如 `projects/DK/DK.md`）。

## 环境准备

1. **安装掘金量化终端**：从[掘金量化官网](https://www.myquant.cn/)下载并安装掘金终端，启动后保持登录（策略运行依赖本地终端提供行情与交易通道）。
2. **Python 环境**：Python 3.11（见 `projects/Small-cap/pyrightconfig.json`）。
3. **安装依赖**：

   ```bash
   pip install gm numpy pandas
   ```

## 配置 Token

策略运行需要掘金账号 token（在掘金终端「系统设置 → 密钥管理」中生成）。推荐通过**环境变量**注入，避免硬编码泄露：

```powershell
# Windows PowerShell
$env:GM_TOKEN = "你的掘金token"
```

```bash
# macOS / Linux
export GM_TOKEN="你的掘金token"
```

> `DK`、`MovLine`、`Small-cap` 已从 `GM_TOKEN` 环境变量读取 token；`EnhancedIndex` 仍为硬编码，建议改为环境变量方式。

## 运行回测

进入任一策略目录，直接运行 `main.py`：

```bash
cd projects/DK
python main.py
```

- 运行前请确保掘金终端已启动并登录。
- 回测区间、初始资金、佣金、滑点等参数在各 `main.py` 的 `run(...)` 中配置。
- 回测结束后，可在掘金终端右上角「回测历史」查看详情；`DK` 策略额外在控制台打印绩效报告。

## 免责声明

本项目所有策略均为**示例，仅供学习与研究**，不构成任何投资建议，未经充分验证请勿直接用于实盘交易。市场有风险，投资需谨慎。
