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
    const [gens, symbolCandles] = await Promise.all([
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
      args,
      symbolCandles,
      gens,
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
                onSelect={(gensInfo, gen) =>
                  setSelectedGenInfo({
                    args: gensInfo.args,
                    config: gen.ind.chromosome,
                    symbolCandles: gensInfo.symbolCandles,
                    symbolStats: gen.symbolStats,
                    symbolSummaries: gen.symbolSummaries,
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
