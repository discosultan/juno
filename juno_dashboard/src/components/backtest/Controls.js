import React from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import Typography from '@material-ui/core/Typography';
import useLocalStorageStateImpl from 'use-local-storage-state';
import DatePicker from '../DatePicker';
import { Strategies, Symbols, Intervals } from '../../info';

function useLocalStorageState(key, defaultValue) {
  return useLocalStorageStateImpl(`backtest_controls_${key}`, defaultValue);
}

export default function Controls({ onBacktest }) {
  const [strategy, setStrategy] = useLocalStorageState('strategy', 'fourweekrule');
  const [exchange, setExchange] = useLocalStorageState('exchange', 'binance');
  const [symbols, setSymbols] = useLocalStorageState('symbols', [
    'eth-btc',
    'ltc-btc',
    'xrp-btc',
    'xmr-btc',
    'ada-btc',
  ]);
  const [interval, setInterval] = useLocalStorageState('interval', '1d');
  const [start, setStart] = useLocalStorageState('start', '2017-12-08');
  const [end, setEnd] = useLocalStorageState('end', '2020-09-30');

  return (
    <form noValidate autoComplete="off">
      <Typography variant="h6" gutterBottom>
        Configure Backtest Args
      </Typography>

      <TextField
        id="strategy"
        label="Strategy"
        fullWidth
        select
        value={strategy}
        onChange={(e) => setStrategy(e.target.value)}
      >
        {Strategies.map((strategy) => (
          <MenuItem key={strategy} value={strategy}>
            {strategy}
          </MenuItem>
        ))}
      </TextField>

      <TextField
        id="exchange"
        fullWidth
        select
        label="Exchange"
        value={exchange}
        onChange={(e) => setExchange(e.target.value)}
      >
        <MenuItem value={'binance'}>Binance</MenuItem>
      </TextField>

      <TextField
        id="symbols"
        label="Symbols"
        fullWidth
        select
        SelectProps={{
          multiple: true,
          value: symbols,
          onChange: (e) => setSymbols(e.target.value),
        }}
      >
        {Symbols.map((symbol) => (
          <MenuItem key={symbol} value={symbol}>
            {symbol}
          </MenuItem>
        ))}
      </TextField>

      <TextField
        id="interval"
        fullWidth
        select
        label="Interval"
        value={interval}
        onChange={(e) => setInterval(e.target.value)}
      >
        {Intervals.map((interval) => (
          <MenuItem key={interval} value={interval}>
            {interval}
          </MenuItem>
        ))}
      </TextField>

      <DatePicker label="Start" value={start} onChange={(e) => setStart(e.target.value)} />
      <DatePicker label="End" value={end} onChange={(e) => setEnd(e.target.value)} />

      <br />
      <br />
      <Button
        fullWidth
        variant="contained"
        onClick={() =>
          onBacktest({
            strategy,
            exchange,
            symbols,
            interval,
            start,
            end,
            quote: 1.0,
          })
        }
      >
        Backtest
      </Button>
    </form>
  );
}
