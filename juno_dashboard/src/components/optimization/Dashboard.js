import React, { useState } from 'react';
import Box from '@material-ui/core/Box';
import Divider from '@material-ui/core/Divider';
import Controls from './Controls';
import History from '../History';
import Generations from './Generations';
import SplitPane from '../SplitPane';
import TradingResult from '../TradingResult';
import { fetchJson } from '../../fetch';

export default function Dashboard() {
  const [gensInfo, setGensInfo] = useState(null);
  const [selectedGenInfo, setSelectedGenInfo] = useState(null);
  // TODO: It would be nice to store the state in local storage. However, it is limited to only
  // 5MB. If we didn't store candle data with it, we could hold more.
  const [history, setHistory] = useState([]);

  function processNewGensInfo(gensInfo) {
    setGensInfo(gensInfo);
    setSelectedGenInfo(null);
  }

  async function optimize(args) {
    const [evolution, symbolCandles] = await Promise.all([
      fetchJson('POST', '/optimize', args),
      fetchJson('POST', '/candles', {
        exchange: args.exchange,
        interval: args.interval,
        start: args.start,
        end: args.end,
        symbols: args.trainingSymbols.concat(args.validationSymbols),
      }),
    ]);
    const gensInfo = {
      args: {
        ...args,
        seed: evolution.seed,
      },
      symbolCandles,
      gens: evolution.generations,
    };

    const historyItem = {
      time: new Date().toISOString(),
      gensInfo,
    };
    if (history.length === 10) {
      setHistory([historyItem, ...history.slice(0, history.length - 1)]);
    } else {
      setHistory([historyItem, ...history]);
    }

    processNewGensInfo(gensInfo);
  }

  return (
    <SplitPane
      left={
        <>
          <Box p={1}>
            <History
              gensInfo={gensInfo}
              history={history}
              onChange={(gensInfo) => processNewGensInfo(gensInfo)}
            />
          </Box>
          <Divider />
          <Box p={1}>
            <Controls onOptimize={optimize} />
          </Box>
        </>
      }
      right={
        <>
          {selectedGenInfo ? (
            <TradingResult value={selectedGenInfo} onClose={() => setSelectedGenInfo(null)} />
          ) : (
            gensInfo && (
              <Generations
                value={gensInfo}
                onSelect={(gensInfo, gen, ind) =>
                  setSelectedGenInfo({
                    args: gensInfo.args,
                    config: {
                      trader: ind.ind.chromosome.trader,
                      strategy: {
                        type: gensInfo.args.strategy,
                        ...ind.ind.chromosome.strategy,
                      },
                      stopLoss: {
                        type: 'legacy',
                        ...ind.ind.chromosome.stopLoss,
                      },
                      takeProfit: {
                        type: 'legacy',
                        ...ind.ind.chromosome.takeProfit,
                      },
                    },
                    symbolCandles: gensInfo.symbolCandles,
                    symbolStats: ind.symbolStats,
                    title: `gen ${gen.nr}`,
                  })
                }
              />
            )
          )}
        </>
      }
    />
  );
}
