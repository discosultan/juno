import React from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import Typography from '@material-ui/core/Typography';
import useLocalStorageStateImpl from 'use-local-storage-state';
import DatePicker from 'components/DatePicker';
import DynamicParams from './DynamicParams';
import {
  Intervals,
  MissedCandlePolicies,
  Strategies,
  StopLosses,
  Symbols,
  TakeProfits,
} from '../../info';

function useLocalStorageState(key, defaultValue) {
  return useLocalStorageStateImpl(`backtest_controls_${key}`, defaultValue);
}

export default function Controls({ onBacktest }) {
  const [exchange, setExchange] = useLocalStorageState('exchange', 'binance');
  const [symbols, setSymbols] = useLocalStorageState('symbols', [
    'eth-btc',
    'ltc-btc',
    'xrp-btc',
    'xmr-btc',
    'ada-btc',
  ]);
  const [interval, setInterval] = useLocalStorageState('interval', '1d');
  const [start, setStart] = useLocalStorageState('start', '2018-01-01');
  const [end, setEnd] = useLocalStorageState('end', '2021-01-01');
  const [missedCandlePolicy, setMissedCandlePolicy] = useLocalStorageState(
    'missedCandlePolicy',
    'ignore',
  );
  const [strategy, setStrategy] = useLocalStorageState('strategy', 'fourweekrule');
  const [strategyParams, setStrategyParams] = useLocalStorageState(
    'strategyParams',
    '{\n  "period": 28,\n  "ma": "kama",\n  "maPeriod": 14\n}',
  );
  const [stopLoss, setStopLoss] = useLocalStorageState('stopLoss', 'basic');
  const [stopLossParams, setStopLossParams] = useLocalStorageState(
    'stopLossParams',
    '{\n  "upThreshold": 0,\n  "downThreshold": 0\n}',
  );
  const [takeProfit, setTakeProfit] = useLocalStorageState('takeProfit', 'basic');
  const [takeProfitParams, setTakeProfitParams] = useLocalStorageState(
    'takeProfitParams',
    '{\n  "upThreshold": 0,\n  "downThreshold": 0\n}',
  );

  return (
    <form noValidate autoComplete="off">
      <Typography variant="h6" gutterBottom>
        Configure Backtest Args
      </Typography>

      <DynamicParams
        label="Strategy"
        options={Strategies}
        value={strategy}
        onChange={(e) => setStrategy(e.target.value)}
        paramsValue={strategyParams}
        paramsOnChange={(e) => setStrategyParams(e.target.value)}
      />

      <DynamicParams
        label="Stop Loss"
        options={StopLosses}
        value={stopLoss}
        onChange={(e) => setStopLoss(e.target.value)}
        paramsValue={stopLossParams}
        paramsOnChange={(e) => setStopLossParams(e.target.value)}
      />

      <DynamicParams
        label="Take Profit"
        options={TakeProfits}
        value={takeProfit}
        onChange={(e) => setTakeProfit(e.target.value)}
        paramsValue={takeProfitParams}
        paramsOnChange={(e) => setTakeProfitParams(e.target.value)}
      />

      <TextField
        id="missedCandlePolicy"
        fullWidth
        select
        label="Missed Candle Policy"
        value={missedCandlePolicy}
        onChange={(e) => setMissedCandlePolicy(e.target.value)}
      >
        {MissedCandlePolicies.map((policy) => (
          <MenuItem key={policy} value={policy}>
            {policy}
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
            missedCandlePolicy,
            strategy,
            strategyParams: JSON.parse(strategyParams),
            stopLoss,
            stopLossParams: JSON.parse(stopLossParams),
            takeProfit,
            takeProfitParams: JSON.parse(takeProfitParams),
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
