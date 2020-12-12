import { fetchJson } from './fetch';

export default class Chandler {
  constructor() {
    this.candles = {}
  }

  async fetchCandles(args) {
    const result = {};
    const missingSymbols = [];

    for (const symbol of args.symbols) {
      const candles = this.candles[getKey(args, symbol)];
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
        this.candles[getKey(args, symbol)] = candles;
      }
    }

    return result;
  }
}

function getKey(args, symbol) {
  return `${args.exchange}_${args.intervals}_${symbol}_${args.start}_${args.end}`;
}
