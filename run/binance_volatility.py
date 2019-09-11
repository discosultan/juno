import asyncio
import logging
import os

import numpy as np
import pandas as pd

from juno.asyncio import list_async
from juno.components import Informant
from juno.exchanges import Binance
from juno.math import floor_multiple
from juno.storages import SQLite
from juno.time import DAY_MS, MONTH_MS, YEAR_MS, time_ms

exchange = 'binance'
symbols = [
    'eth-btc', 'ltc-btc', 'bnb-btc', 'neo-btc', 'qtum-eth', 'eos-eth', 'snt-eth', 'bnt-eth',
    # 'bcc-btc', 'gas-btc', 'bnb-eth', 'btc-usdt', 'eth-usdt', 'hsr-btc', 'oax-eth', 'dnt-eth',
    # 'mco-eth', 'icn-eth', 'mco-btc', 'wtc-btc', 'wtc-eth', 'lrc-btc', 'lrc-eth', 'qtum-btc',
    # 'yoyo-btc', 'omg-btc', 'omg-eth', 'zrx-btc', 'zrx-eth', 'strat-btc', 'strat-eth', 'sngls-btc',
    # 'sngls-eth', 'bqx-btc', 'bqx-eth', 'knc-btc', 'knc-eth', 'fun-btc', 'fun-eth', 'snm-btc',
    # 'snm-eth', 'neo-eth', 'iota-btc', 'iota-eth', 'link-btc', 'link-eth', 'xvg-btc', 'xvg-eth',
    # 'salt-btc', 'salt-eth', 'mda-btc', 'mda-eth', 'mtl-btc', 'mtl-eth', 'sub-btc', 'sub-eth',
    # 'eos-btc', 'snt-btc', 'etc-eth', 'etc-btc', 'mth-btc', 'mth-eth', 'eng-btc', 'eng-eth',
    # 'dnt-btc', 'zec-btc', 'zec-eth', 'bnt-btc', 'ast-btc', 'ast-eth', 'dash-btc', 'dash-eth',
    # 'oax-btc', 'icn-btc', 'btg-btc', 'btg-eth', 'evx-btc', 'evx-eth', 'req-btc', 'req-eth',
    # 'vib-btc', 'vib-eth', 'hsr-eth', 'trx-btc', 'trx-eth', 'powr-btc', 'powr-eth', 'ark-btc',
    # 'ark-eth', 'yoyo-eth', 'xrp-btc', 'xrp-eth', 'mod-btc', 'mod-eth', 'enj-btc', 'enj-eth',
    # 'storj-btc', 'storj-eth', 'bnb-usdt', 'ven-bnb', 'yoyo-bnb', 'powr-bnb', 'ven-btc', 'ven-eth',
    # 'kmd-btc', 'kmd-eth', 'nuls-bnb', 'rcn-btc', 'rcn-eth', 'rcn-bnb', 'nuls-btc', 'nuls-eth',
    # 'rdn-btc', 'rdn-eth', 'rdn-bnb', 'xmr-btc', 'xmr-eth', 'dlt-bnb', 'wtc-bnb', 'dlt-btc',
    # 'dlt-eth', 'amb-btc', 'amb-eth', 'amb-bnb', 'bcc-eth', 'bcc-usdt', 'bcc-bnb', 'bat-btc',
    # 'bat-eth', 'bat-bnb', 'bcpt-btc', 'bcpt-eth', 'bcpt-bnb', 'arn-btc', 'arn-eth', 'gvt-btc',
    # 'gvt-eth', 'cdt-btc', 'cdt-eth', 'gxs-btc', 'gxs-eth', 'neo-usdt', 'neo-bnb', 'poe-btc',
    # 'poe-eth', 'qsp-btc', 'qsp-eth', 'qsp-bnb', 'bts-btc', 'bts-eth', 'bts-bnb', 'xzc-btc',
    # 'xzc-eth', 'xzc-bnb', 'lsk-btc', 'lsk-eth', 'lsk-bnb', 'tnt-btc', 'tnt-eth', 'fuel-btc',
    # 'fuel-eth', 'mana-btc', 'mana-eth', 'bcd-btc', 'bcd-eth', 'dgd-btc', 'dgd-eth', 'iota-bnb',
    # 'adx-btc', 'adx-eth', 'adx-bnb', 'ada-btc', 'ada-eth', 'ppt-btc', 'ppt-eth', 'cmt-btc',
    # 'cmt-eth', 'cmt-bnb', 'xlm-btc', 'xlm-eth', 'xlm-bnb', 'cnd-btc', 'cnd-eth', 'cnd-bnb',
    # 'lend-btc', 'lend-eth', 'wabi-btc', 'wabi-eth', 'wabi-bnb', 'ltc-eth', 'ltc-usdt', 'ltc-bnb',
    # 'tnb-btc', 'tnb-eth', 'waves-btc', 'waves-eth', 'waves-bnb', 'gto-btc', 'gto-eth', 'gto-bnb',
    # 'icx-btc', 'icx-eth', 'icx-bnb', 'ost-btc', 'ost-eth', 'ost-bnb', 'elf-btc', 'elf-eth',
    # 'aion-btc', 'aion-eth', 'aion-bnb', 'nebl-btc', 'nebl-eth', 'nebl-bnb', 'brd-btc', 'brd-eth',
    # 'brd-bnb', 'mco-bnb', 'edo-btc', 'edo-eth', 'wings-btc', 'wings-eth', 'nav-btc', 'nav-eth',
    # 'nav-bnb', 'lun-btc', 'lun-eth', 'trig-btc', 'trig-eth', 'trig-bnb', 'appc-btc', 'appc-eth',
    # 'appc-bnb', 'vibe-btc', 'vibe-eth', 'rlc-btc', 'rlc-eth', 'rlc-bnb', 'ins-btc', 'ins-eth',
    # 'pivx-btc', 'pivx-eth', 'pivx-bnb', 'iost-btc', 'iost-eth', 'chat-btc', 'chat-eth',
    # 'steem-btc', 'steem-eth', 'steem-bnb', 'nano-btc', 'nano-eth', 'nano-bnb', 'via-btc',
    # 'via-eth', 'via-bnb', 'blz-btc', 'blz-eth', 'blz-bnb', 'ae-btc', 'ae-eth', 'ae-bnb', 'rpx-btc',
    # 'rpx-eth', 'rpx-bnb', 'ncash-btc', 'ncash-eth', 'ncash-bnb', 'poa-btc', 'poa-eth', 'poa-bnb',
    # 'zil-btc', 'zil-eth', 'zil-bnb', 'ont-btc', 'ont-eth', 'ont-bnb', 'storm-btc', 'storm-eth',
    # 'storm-bnb', 'qtum-bnb', 'qtum-usdt', 'xem-btc', 'xem-eth', 'xem-bnb', 'wan-btc', 'wan-eth',
    # 'wan-bnb', 'wpr-btc', 'wpr-eth', 'qlc-btc', 'qlc-eth', 'sys-btc', 'sys-eth', 'sys-bnb',
    # 'qlc-bnb', 'grs-btc', 'grs-eth', 'ada-usdt', 'ada-bnb', 'cloak-btc', 'cloak-eth', 'gnt-btc',
    # 'gnt-eth', 'gnt-bnb', 'loom-btc', 'loom-eth', 'loom-bnb', 'xrp-usdt', 'bcn-btc', 'bcn-eth',
    # 'bcn-bnb', 'rep-btc', 'rep-eth', 'rep-bnb', 'btc-tusd', 'tusd-btc', 'eth-tusd', 'tusd-eth',
    # 'tusd-bnb', 'zen-btc', 'zen-eth', 'zen-bnb', 'sky-btc', 'sky-eth', 'sky-bnb', 'eos-usdt',
    # 'eos-bnb', 'cvc-btc', 'cvc-eth', 'cvc-bnb', 'theta-btc', 'theta-eth', 'theta-bnb', 'xrp-bnb',
    # 'tusd-usdt', 'iota-usdt', 'xlm-usdt', 'iotx-btc', 'iotx-eth', 'qkc-btc', 'qkc-eth', 'agi-btc',
    # 'agi-eth', 'agi-bnb', 'nxs-btc', 'nxs-eth', 'nxs-bnb', 'enj-bnb', 'data-btc', 'data-eth',
    # 'ont-usdt', 'trx-bnb', 'trx-usdt', 'etc-usdt', 'etc-bnb', 'icx-usdt', 'sc-btc', 'sc-eth',
    # 'sc-bnb', 'npxs-btc', 'npxs-eth', 'ven-usdt', 'key-btc', 'key-eth', 'nas-btc', 'nas-eth',
    # 'nas-bnb', 'mft-btc', 'mft-eth', 'mft-bnb', 'dent-btc', 'dent-eth', 'ardr-btc', 'ardr-eth',
    # 'ardr-bnb', 'nuls-usdt', 'hot-btc', 'hot-eth', 'vet-btc', 'vet-eth', 'vet-usdt', 'vet-bnb',
    # 'dock-btc', 'dock-eth', 'poly-btc', 'poly-bnb', 'phx-btc', 'phx-eth', 'phx-bnb', 'hc-btc',
    # 'hc-eth', 'go-btc', 'go-bnb', 'pax-btc', 'pax-bnb', 'pax-usdt', 'pax-eth', 'rvn-btc',
    # 'rvn-bnb', 'dcr-btc', 'dcr-bnb', 'usdc-bnb', 'usdc-btc', 'mith-btc', 'mith-bnb', 'bchabc-btc',
    # 'bchsv-btc', 'bchabc-usdt', 'bchsv-usdt', 'bnb-pax', 'btc-pax', 'eth-pax', 'xrp-pax',
    # 'eos-pax', 'xlm-pax', 'ren-btc', 'ren-bnb', 'bnb-tusd', 'xrp-tusd', 'eos-tusd', 'xlm-tusd',
    # 'bnb-usdc', 'btc-usdc', 'eth-usdc', 'xrp-usdc', 'eos-usdc', 'xlm-usdc', 'usdc-usdt',
    # 'ada-tusd', 'trx-tusd', 'neo-tusd', 'trx-xrp', 'xzc-xrp', 'pax-tusd', 'usdc-tusd', 'usdc-pax',
    # 'link-usdt', 'link-tusd', 'link-pax', 'link-usdc', 'waves-usdt', 'waves-tusd', 'waves-pax',
    # 'waves-usdc', 'bchabc-tusd', 'bchabc-pax', 'bchabc-usdc', 'bchsv-tusd', 'bchsv-pax',
    # 'bchsv-usdc', 'ltc-tusd', 'ltc-pax', 'ltc-usdc', 'trx-pax', 'trx-usdc', 'btt-btc', 'btt-bnb',
    # 'btt-usdt', 'bnb-usds', 'btc-usds', 'usds-usdt', 'usds-pax', 'usds-tusd', 'usds-usdc',
    # 'btt-pax', 'btt-tusd', 'btt-usdc', 'ong-bnb', 'ong-btc', 'ong-usdt', 'hot-bnb', 'hot-usdt',
    # 'zil-usdt', 'zrx-bnb', 'zrx-usdt', 'fet-bnb', 'fet-btc', 'fet-usdt', 'bat-usdt', 'xmr-bnb',
    # 'xmr-usdt', 'zec-bnb', 'zec-usdt', 'zec-pax', 'zec-tusd', 'zec-usdc', 'iost-bnb', 'iost-usdt',
    # 'celr-bnb', 'celr-btc', 'celr-usdt', 'ada-pax', 'ada-usdc', 'neo-pax', 'neo-usdc', 'dash-bnb',
    # 'dash-usdt', 'nano-usdt', 'omg-bnb', 'omg-usdt', 'theta-usdt', 'enj-usdt', 'mith-usdt',
    # 'matic-bnb', 'matic-btc', 'matic-usdt', 'atom-bnb', 'atom-btc', 'atom-usdt', 'atom-usdc',
    # 'atom-pax', 'atom-tusd', 'etc-usdc', 'etc-pax', 'etc-tusd', 'bat-usdc', 'bat-pax', 'bat-tusd',
    # 'phb-bnb', 'phb-btc', 'phb-usdc', 'phb-tusd', 'phb-pax', 'tfuel-bnb', 'tfuel-btc',
    # 'tfuel-usdt', 'tfuel-usdc', 'tfuel-tusd', 'tfuel-pax', 'one-bnb', 'one-btc', 'one-usdt',
    # 'one-tusd', 'one-pax', 'one-usdc', 'ftm-bnb', 'ftm-btc', 'ftm-usdt', 'ftm-tusd', 'ftm-pax',
    # 'ftm-usdc', 'btcb-btc', 'bcpt-tusd', 'bcpt-pax', 'bcpt-usdc', 'algo-bnb', 'algo-btc',
    # 'algo-usdt', 'algo-tusd', 'algo-pax', 'algo-usdc', 'usdsb-usdt', 'usdsb-usds', 'gto-usdt',
    # 'gto-pax', 'gto-tusd', 'gto-usdc', 'erd-bnb', 'erd-btc', 'erd-usdt', 'erd-pax', 'erd-usdc',
    # 'doge-bnb', 'doge-btc', 'doge-usdt', 'doge-pax', 'doge-usdc', 'dusk-bnb', 'dusk-btc',
    # 'dusk-usdt', 'dusk-usdc', 'dusk-pax', 'bgbp-usdc', 'ankr-bnb', 'ankr-btc', 'ankr-usdt',
    # 'ankr-tusd', 'ankr-pax', 'ankr-usdc', 'ont-pax', 'ont-usdc', 'win-bnb', 'win-btc', 'win-usdt',
    # 'win-usdc', 'cos-bnb', 'cos-btc', 'cos-usdt', 'tusdb-tusd', 'npxs-usdt', 'npxs-usdc',
    # 'cocos-bnb', 'cocos-btc', 'cocos-usdt', 'mtl-usdt', 'tomo-bnb', 'tomo-btc', 'tomo-usdt',
    # 'tomo-usdc', 'perl-bnb', 'perl-btc', 'perl-usdc', 'perl-usdt', 'dent-usdt', 'mft-usdt',
    # 'key-usdt', 'storm-usdt', 'dock-usdt', 'wan-usdt', 'fun-usdt', 'cvc-usdt', 'btt-trx',
    # 'win-trx', 'chz-bnb', 'chz-btc', 'chz-usdt'
]
interval = DAY_MS
end = floor_multiple(time_ms(), interval)
start = end - MONTH_MS


async def find_volatility_for_symbol(informant, exchange, symbol, interval, start, end):
    candles = await list_async(informant.stream_candles(exchange, symbol, interval, start, end))
    df = pd.DataFrame([float(c.close) for c in candles], columns=['price'])
    # Find returns.
    df['pct_chg'] = df['price'].pct_change()
    # Find log returns.
    df['log_ret'] = np.log(1 + df['pct_chg'])
    # df['log_ret'] = np.log(df['price']) - np.log(df['price'].shift(1))
    # Find volatility.
    volatility = df['log_ret'].std(ddof=0)
    annualized_volatility = volatility * ((YEAR_MS / interval)**0.5)
    return symbol, annualized_volatility


async def main():
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    async with binance, informant:
        tasks = []
        for symbol in symbols:
            tasks.append(
                find_volatility_for_symbol(informant, exchange, symbol, interval, start, end)
            )
        results = await asyncio.gather(*tasks)

        def by_volatility(value):
            return value[1]

        best = max(results, key=by_volatility)
        print(results)
        print(best)


logging.basicConfig(level='WARNING')
asyncio.run(main())
