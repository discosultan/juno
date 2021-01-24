import { useEffect, useState } from 'react';
import { fetchJson } from 'fetch';

const candleCache = {};

export default function useSymbolCandles(args) {
  const [symbolCandles, setSymbolCandles] = useState({});

  useEffect(() => {
    (async () => {
      setSymbolCandles(
        await fetchCandles({
          exchange: args.exchange,
          interval: args.interval,
          start: args.start,
          end: args.end,
          symbols: args.trainingSymbols.concat(args.validationSymbols),
        }),
      );
    })();
  }, [args]);

  return symbolCandles;
}

async function fetchCandles(args) {
  const result = {};
  const missingSymbols = [];

  for (const symbol of args.symbols) {
    const candles = candleCache[composeKey(args, symbol)];
    if (candles === undefined) {
      missingSymbols.push(symbol);
    } else {
      result[symbol] = candles;
    }
  }

  if (missingSymbols.length > 0) {
    const missingCandles = await fetchJson('POST', '/candles', {
      exchange: args.exchange,
      interval: args.interval,
      start: args.start,
      end: args.end,
      symbols: missingSymbols,
    });
    for (const [symbol, candles] of Object.entries(missingCandles)) {
      result[symbol] = candles;
      candleCache[composeKey(args, symbol)] = candles;
    }
  }

  return result;
}

function composeKey(args, symbol) {
  return `${args.exchange}_${args.intervals}_${symbol}_${args.start}_${args.end}`;
}
