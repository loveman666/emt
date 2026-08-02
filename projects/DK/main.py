# coding=utf-8
from __future__ import absolute_import, print_function

import datetime
import os
import sys
from collections import deque

from gm.api import *


# 回测初始资金（模块级，供 run 与报告共用）
INITIAL_CASH = 100000


'''
示例策略仅供参考，不建议未经验证直接用于实盘。

本策略参考东方财富 DK 指标（多空指标）实现择时买卖点，交易标的为
上交所半导体ETF（SHSE.512480）：

DK 指标原理（社区逆向拟合的通行近似版）：
1. RSV = (Close - LLV(Low, N)) / (HHV(High, N) - LLV(Low, N)) * 100
   衡量当前价格在最近 N 根 K 线区间中的相对位置（0=底部，100=顶部）。
2. 对 RSV 做两次 SMA(x, m, 1) 递推平滑，得到多空能量线 DK 及其信号线 MDK：
       SMA(x, m, 1) 的递推式：Y = (X + (m - 1) * Y_prev) / m
       DK  = SMA(RSV, M, 1)
       MDK = SMA(DK,  M, 1)
3. 状态机翻转 + 阈值过滤，保证买卖点交替出现（不连续买 / 连续卖）：
   - 当前为空头，且 DK 于低位（DK < LOW_TH）上穿 MDK  -> D 买点，切多头，95% 建仓
   - 当前为多头，且 DK 先冲上 ARM_LEVEL 后回落跌破 EXIT_LEVEL -> K 卖点，切空头，清仓
     （追踪出场，避免强趋势中 DK 长期钉在高位反复金叉死叉导致过早离场）

A股及ETF不做空，因此策略只持有多仓或空仓。
'''


def init(context):
    context.symbol = 'SHSE.512480'
    context.frequency = '1800s'

    # DK 指标参数
    context.n_period = 34        # 区间回看周期 N
    context.smooth_period = 5    # SMA 平滑周期 M
    context.low_threshold = 25   # 低位阈值：DK 低于此值的金叉才视为买点
    # 追踪出场参数：持仓期间 DK 需先冲上 arm_level（武装），
    # 随后回落跌破 exit_level 才触发 K 卖点。
    # 避免强趋势中 DK 长期钉在高位反复金叉死叉导致过早离场。
    context.arm_level = 80       # 高位武装阈值
    context.exit_level = 50      # 回落出场阈值

    context.target_percent = 0.95

    # 计算 RSV 需要最近 N 根的 high/low，故窗口长度为 N
    context.high_window = deque(maxlen=context.n_period)
    context.low_window = deque(maxlen=context.n_period)

    # SMA 递推需要保存上一根的 DK / MDK 值
    context.prev_dk = None
    context.prev_mdk = None
    # 上一根的 DK-MDK 差值，用于判定穿越
    context.prev_diff = None
    # 多空状态：True=多头（已持仓），False=空头（空仓）
    context.is_long = False
    # 追踪出场武装标志：持仓期间 DK 是否已冲上 arm_level
    context.armed = False

    context.market_data_connected = True
    context.last_market_error_time = None

    # 回测不预取开始日前数据；实盘预取指标所需数据。
    subscribe_count = 0 if context.mode == MODE_BACKTEST else context.n_period
    subscribe(
        context.symbol,
        context.frequency,
        count=subscribe_count,
        unsubscribe_previous=True,
    )


def _sma(x, prev, period):
    '''通达信 SMA(X, M, 1) 递推：Y = (X + (M - 1) * Y_prev) / M

    首次计算（prev 为 None）时以 X 作为初值。
    '''
    if prev is None:
        return x
    return (x + (period - 1) * prev) / period


def on_bar(context, bars):
    if not context.market_data_connected or not bars:
        return

    bar = bars[0]
    symbol = bar['symbol']
    if symbol != context.symbol:
        return

    context.high_window.append(float(bar['high']))
    context.low_window.append(float(bar['low']))

    # 数据不足 N 根，无法计算区间位置
    if len(context.high_window) < context.n_period:
        return

    hhv = max(context.high_window)
    llv = min(context.low_window)
    price_range = hhv - llv

    # 区间为 0（极端一字行情）时跳过，避免除零
    if price_range == 0:
        return

    close = float(bar['close'])
    rsv = (close - llv) / price_range * 100.0

    # 两次 SMA 平滑得到 DK 与信号线 MDK
    dk = _sma(rsv, context.prev_dk, context.smooth_period)
    mdk = _sma(dk, context.prev_mdk, context.smooth_period)

    diff = dk - mdk
    prev_diff = context.prev_diff

    # 更新递推状态（放在信号判定之前保存本根值供下根使用）
    context.prev_dk = dk
    context.prev_mdk = mdk
    context.prev_diff = diff

    # 首根平滑值无前值可比，无法判定穿越
    if prev_diff is None:
        return

    golden_cross = prev_diff <= 0 and diff > 0   # DK 上穿 MDK

    # 与实际持仓核对，避免状态与持仓不一致
    positions = get_position() or []
    has_long_position = any(
        position['symbol'] == symbol
        and position['side'] == PositionSide_Long
        and position.get('volume', 0) > 0
        for position in positions
    )

    # D 买点：空头状态 + 低位金叉
    if (
        not context.is_long
        and golden_cross
        and dk < context.low_threshold
        and not has_long_position
    ):
        order_target_percent(
            symbol=symbol,
            percent=context.target_percent,
            position_side=PositionSide_Long,
            order_type=OrderType_Market,
        )
        context.is_long = True
        context.armed = False
        print(
            '{}：{} DK买点(D)，DK={:.2f} MDK={:.2f} 低位金叉，目标仓位{:.0%}'.format(
                context.now, symbol, dk, mdk, context.target_percent,
            )
        )
        return

    # K 卖点：多头状态 + 追踪出场（DK 曾冲上 arm_level 后回落跌破 exit_level）
    if context.is_long:
        if dk > context.arm_level:
            context.armed = True

        if context.armed and dk < context.exit_level:
            if has_long_position:
                order_target_percent(
                    symbol=symbol,
                    percent=0,
                    position_side=PositionSide_Long,
                    order_type=OrderType_Market,
                )
                print(
                    '{}：{} DK卖点(K)，DK={:.2f} MDK={:.2f} 高位回落，清空持仓'.format(
                        context.now, symbol, dk, mdk,
                    )
                )
            context.is_long = False
            context.armed = False


def on_order_status(context, order):
    if order['status'] != 3:
        return

    side_text = '买入' if order['side'] == OrderSide_Buy else '卖出'
    order_type_text = (
        '限价' if order['order_type'] == OrderType_Limit else '市价'
    )
    print(
        '{}：标的：{}，操作：{}{}，成交价格：{}，成交数量：{}'.format(
            context.now,
            order['symbol'],
            order_type_text,
            side_text,
            order['price'],
            order['volume'],
        )
    )


def on_error(context, code, info):
    error_code = str(code)
    now = datetime.datetime.now()

    if error_code in ('1200', '1201'):
        context.market_data_connected = False
        last_time = context.last_market_error_time
        if last_time is None or (now - last_time).total_seconds() >= 60:
            print(
                '{}：行情连接异常，错误码={}，{}；SDK正在自动重连。'.format(
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                    error_code,
                    info,
                )
            )
            context.last_market_error_time = now
        return

    print(
        '{}：GM错误，错误码={}，信息={}'.format(
            now.strftime('%Y-%m-%d %H:%M:%S'),
            error_code,
            info,
        )
    )


def on_market_data_connected(context):
    context.market_data_connected = True
    context.last_market_error_time = None
    print(
        '{}：行情服务已连接，策略恢复接收行情。'.format(
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
    )


def on_market_data_disconnected(context):
    context.market_data_connected = False
    print(
        '{}：行情服务已断开，暂停处理交易信号。{}'.format(
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            getattr(context, 'message', ''),
        )
    )


def on_backtest_finished(context, indicator):
    print('=' * 56)
    print('DK 策略回测报告')
    print('=' * 56)

    # 基本信息
    print('标的            ：{}'.format(context.symbol))
    print('周期            ：{}'.format(context.frequency))
    print('DK 参数         ：N={} M={} 买入阈值={} 武装={} 出场={}'.format(
        context.n_period, context.smooth_period,
        context.low_threshold, context.arm_level, context.exit_level,
    ))
    print('回测区间        ：{} ~ {}'.format(
        getattr(context, 'backtest_start_time', '-'),
        getattr(context, 'backtest_end_time', '-'),
    ))

    # 期末权益与初始资金（以 indicator 累计收益率为准，口径一致）
    init_cash = INITIAL_CASH
    pnl_ratio_val = (
        indicator.get('pnl_ratio') if isinstance(indicator, dict)
        else getattr(indicator, 'pnl_ratio', None)
    )
    print('初始资金        ：{:,.2f}'.format(init_cash))
    if pnl_ratio_val is not None:
        final_nav = init_cash * (1 + pnl_ratio_val)
        print('期末总权益      ：{:,.2f}'.format(final_nav))
        print('净盈亏          ：{:,.2f}'.format(final_nav - init_cash))

    print('-' * 56)
    print('绩效指标：')

    def _get(key):
        if isinstance(indicator, dict):
            return indicator.get(key)
        return getattr(indicator, key, None)

    fields = [
        ('pnl_ratio', '累计收益率', '{:.2%}'),
        ('pnl_ratio_annual', '年化收益率', '{:.2%}'),
        ('sharp_ratio', '夏普比率', '{:.4f}'),
        ('max_drawdown', '最大回撤', '{:.2%}'),
        ('calmar_ratio', 'Calmar比率', '{:.4f}'),
        ('sortino_ratio', 'Sortino比率', '{:.4f}'),
        ('risk_ratio', '风险度', '{:.2%}'),
        ('open_count', '开仓次数', '{}'),
        ('close_count', '平仓次数', '{}'),
        ('win_count', '盈利次数', '{}'),
        ('lose_count', '亏损次数', '{}'),
        ('win_ratio', '胜率', '{:.2%}'),
    ]
    for key, label, fmt in fields:
        value = _get(key)
        if value is None:
            continue
        try:
            print('  {:<12}：{}'.format(label, fmt.format(value)))
        except (ValueError, TypeError):
            print('  {:<12}：{}'.format(label, value))

    print('=' * 56)
    print('回测已完成，也可通过掘金终端右上角“回测历史”查询详情。')


if __name__ == '__main__':
    # 保证中文在 Windows 控制台正常显示
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    now = datetime.datetime.now()
    # 账号数据权限限制：仅可取最近约 180 个自然日，留安全边界取 178 天
    backtest_start_time = (
        now - datetime.timedelta(days=178)
    ).strftime('%Y-%m-%d 09:30:00')
    backtest_end_time = now.strftime('%Y-%m-%d 15:00:00')

    token = os.getenv('GM_TOKEN')
    if not token:
        raise RuntimeError('请先设置环境变量 GM_TOKEN')

    run(
        strategy_id='888f65c9-8cf8-11f1-a9c3-00ffaff73282',
        filename='main.py',
        mode=MODE_BACKTEST,
        token=token,
        backtest_start_time=backtest_start_time,
        backtest_end_time=backtest_end_time,
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=INITIAL_CASH,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
        backtest_match_mode=0,
    )
