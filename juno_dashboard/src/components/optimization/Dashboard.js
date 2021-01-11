import React, { useState } from 'react';
import Box from '@material-ui/core/Box';
import Divider from '@material-ui/core/Divider';
import useLocalStorageState from 'use-local-storage-state';
import Controls from './Controls';
import History from '../History';
import Generations from './Generations';
import SplitPane from '../SplitPane';
import TradingResult from '../TradingResult';
import { fetchJson } from '../../fetch';

export default function Dashboard() {
  const [gensInfo, setGensInfo] = useState(null);
  const [selectedGenInfo, setSelectedGenInfo] = useState(null);
  const [history, setHistory] = useLocalStorageState('optimization_dashboard_history', []);

  function processGensInfo(gensInfo) {
    setGensInfo(gensInfo);
    setSelectedGenInfo(null);
  }

  async function optimize(args) {
    const evolution = await fetchJson(
      'POST',
      `/optimize/${args.strategy}/${args.stopLoss}/${args.takeProfit}`,
      args,
    );
    const gensInfo = {
      args: {
        ...args,
        seed: evolution.seed,
      },
      gens: evolution.generations,
    };

    const historyItem = {
      time: new Date().toISOString(),
      value: gensInfo,
    };
    if (history.length === 10) {
      setHistory([historyItem, ...history.slice(0, history.length - 1)]);
    } else {
      setHistory([historyItem, ...history]);
    }

    processGensInfo(gensInfo);
  }

  return (
    <SplitPane
      left={
        <>
          <Box p={1}>
            <History
              id="optimization-history"
              label="Optimization History"
              value={gensInfo}
              history={history}
              format={(gensInfo) => gensInfo.args.strategy}
              onChange={(gensInfo) => processGensInfo(gensInfo)}
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
                      missedCandlePolicy: ind.ind.chromosome.missedCandlePolicy,
                      strategy: {
                        type: gensInfo.args.strategy,
                        ...ind.ind.chromosome.strategy,
                      },
                      stopLoss: {
                        type: gensInfo.args.stopLoss,
                        ...ind.ind.chromosome.stopLoss,
                      },
                      takeProfit: {
                        type: gensInfo.args.takeProfit,
                        ...ind.ind.chromosome.takeProfit,
                      },
                    },
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
