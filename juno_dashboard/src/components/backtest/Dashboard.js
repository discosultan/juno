import React, { useState } from 'react';
import Box from '@material-ui/core/Box';
import ControlPanel from './ControlPanel';
import SplitPane from '../SplitPane';
import TradingResult from '../TradingResult';
import { fetchJson } from '../../fetch';

export default function Dashboard() {
    const [tradingResult, setTradingResult] = useState(null);

    async function backtest(args) {
        const [result, symbolCandles] = await Promise.all([
            fetchJson('POST', '/backtest', args),
            fetchJson('POST', '/candles', {
                exchange: args.exchange,
                interval: args.interval,
                start: args.start,
                end: args.end,
                symbols: args.symbols,
            }),
        ]);

        setTradingResult({
            args: {
                trainingSymbols: [],
                validationSymbols: args.symbols,
            },
            config: args.config,
            symbolCandles,
            symbolStats: result.symbolStats,
            symbolSummaries: result.symbolSummaries,
            title: args.strategy,
        });
    }

    return (
        <SplitPane
            left={
                <Box p={1}>
                    <ControlPanel onBacktest={backtest} />
                </Box>
            }
            right={tradingResult && <TradingResult value={tradingResult}/>}
        />
    );
}
