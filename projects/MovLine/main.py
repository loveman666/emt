# coding=utf-8
from __future__ import absolute_import, print_function

import datetime
import os
from collections import deque

from gm.api import *


'''
示例策略仅供参考，不建议未经验证直接用于实盘。

本策略使用5分钟K线建立20/60周期双均线模型，交易标的为
上交所半导体ETF（SHSE.512480）：
1. 短期均线上穿长期均线时，以95%的目标仓位买入；
2. 短期均线下穿长期均线时，清空持仓；
3. A股及ETF不做空，因此策略只持有多仓或空仓。
'''


def init(context):
    context.symbol = 'SHSE.512480'
    context.frequency = '300s'
    context.short_period = 20
    context.long_period = 60
    context.data_count = context.long_period + 1
    context.target_percent = 0.95
    context.close_window = deque(maxlen=context.data_count)
    context.market_data_connected = True
    context.last_market_error_time = None

    # 回测不预取开始日前数据；实盘预取均线所需数据。
    subscribe_count = 0 if context.mode == MODE_BACKTEST else context.data_count
    subscribe(
        context.symbol,
        context.frequency,
        count=subscribe_count,
        unsubscribe_previous=True,
    )


def on_bar(context, bars):
    if not context.market_data_connected or not bars:
        return

    symbol = bars[0]['symbol']
    if symbol != context.symbol:
        return

    context.close_window.append(float(bars[0]['close']))
    if len(context.close_window) < context.data_count:
        return

    closes = list(context.close_window)
    previous_short = sum(closes[-21:-1]) / context.short_period
    current_short = sum(closes[-20:]) / context.short_period
    previous_long = sum(closes[-61:-1]) / context.long_period
    current_long = sum(closes[-60:]) / context.long_period

    positions = get_position() or []
    has_long_position = any(
        position['symbol'] == symbol
        and position['side'] == PositionSide_Long
        and position.get('volume', 0) > 0
        for position in positions
    )

    golden_cross = (
        previous_short <= previous_long and current_short > current_long
    )
    death_cross = (
        previous_short >= previous_long and current_short < current_long
    )

    if golden_cross and not has_long_position:
        order_target_percent(
            symbol=symbol,
            percent=context.target_percent,
            position_side=PositionSide_Long,
            order_type=OrderType_Market,
        )
        print(
            '{}：{} 金叉，目标仓位调整为{:.0%}'.format(
                context.now,
                symbol,
                context.target_percent,
            )
        )
    elif death_cross and has_long_position:
        order_target_percent(
            symbol=symbol,
            percent=0,
            position_side=PositionSide_Long,
            order_type=OrderType_Market,
        )
        print('{}：{} 死叉，清空持仓'.format(context.now, symbol))


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
    print('*' * 50)
    print('回测已完成，请通过右上角“回测历史”功能查询详情。')


if __name__ == '__main__':
    now = datetime.datetime.now()
    backtest_start_time = (
        now - datetime.timedelta(days=180)
    ).strftime('%Y-%m-%d 09:30:00')
    backtest_end_time = now.strftime('%Y-%m-%d 15:00:00')

    token = os.getenv('GM_TOKEN')
    if not token:
        raise RuntimeError('请先设置环境变量 GM_TOKEN')

    run(
        strategy_id='e9ca8b9f-88a5-11f1-ac04-00ffaff73282',
        filename='main.py',
        mode=MODE_BACKTEST,
        token=token,
        backtest_start_time=backtest_start_time,
        backtest_end_time=backtest_end_time,
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=100000,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
        backtest_match_mode=0,
    )
