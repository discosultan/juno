import React, { useState } from 'react';
import Box from '@material-ui/core/Box';
import Divider from '@material-ui/core/Divider';
import useLocalStorageState from 'use-local-storage-state';
import History from 'components/History';
import SplitPane from 'components/SplitPane';
import TradingResult from 'components/TradingResult';
import { fetchJson } from 'fetch';
import Controls from './Controls';

export default function Dashboard() {
  const [tradingResult, setTradingResult] = useState(null);
  const [history, setHistory] = useLocalStorageState('backtest_dashboard_history', []);

  async function backtest(args) {
    const result = await fetchJson(
      'POST',
      `/backtest/${args.strategy}/${args.stopLoss}/${args.takeProfit}`,
      args,
    );

    const tradingResult = {
      args: {
        exchange: args.exchange,
        start: args.start,
        end: args.end,
        trainingSymbols: args.symbols,
        validationSymbols: [],
      },
      config: {
        strategy: {
          type: args.strategy,
          ...args.strategyParams,
        },
        stopLoss: {
          type: args.stopLoss,
          ...args.stopLossParams,
        },
        takeProfit: {
          type: args.takeProfit,
          ...args.takeProfitParams,
        },
        trader: {
          interval: args.interval,
          missedCandlePolicy: args.missedCandlePolicy,
        },
      },
      symbolStats: result.symbolStats,
      title: args.strategy,
    };

    const historyItem = {
      time: new Date().toISOString(),
      value: tradingResult,
    };
    if (history.length === 10) {
      setHistory([historyItem, ...history.slice(0, history.length - 1)]);
    } else {
      setHistory([historyItem, ...history]);
    }

    setTradingResult(tradingResult);
  }

  return (
    <SplitPane
      left={
        <>
          <Box p={1}>
            <History
              id="backtest-history"
              label="Backtest History"
              value={tradingResult}
              history={history}
              format={(tradingResult) => tradingResult.config.strategy.type}
              onChange={(tradingResult) => setTradingResult(tradingResult)}
            />
          </Box>
          <Divider />
          <Box p={1}>
            <Controls onBacktest={backtest} />
          </Box>
        </>
      }
      right={tradingResult && <TradingResult value={tradingResult} />}
    />
  );
}
