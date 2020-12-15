import React, { useContext, useEffect, useState } from 'react';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';
import Button from '@material-ui/core/Button';
import Chart from './Chart';
import { ChandlerContext } from '../App';

export default function TradingResult({ value, onClose }) {
  const { args, config, symbolStats, title } = value;
  const stats = Object.values(symbolStats);
  const chandler = useContext(ChandlerContext);
  const [symbolCandles, setSymbolCandles] = useState(null);

  useEffect(() => {
    (async () => {
      setSymbolCandles(
        await chandler.fetchCandles({
          exchange: args.exchange,
          interval: args.interval,
          start: args.start,
          end: args.end,
          symbols: args.trainingSymbols.concat(args.validationSymbols),
        }),
      );
    })();
  }, [args, chandler]);

  function renderStats() {
    if (stats.length === 0) return <></>;

    const keys = Object.keys(stats[0]).filter((key) => key !== 'positions');
    const symbols = args.trainingSymbols.concat(args.validationSymbols);

    const keyTotals = keys.map((key) => symbols.reduce((acc, symbol) => {
      const value = symbolStats[symbol][key];
      return typeof value === "number" ? acc + value : acc;
    }, 0));

    return (
      keys
        .map((key, i) => (
          <TableRow key={key}>
            <TableCell component="th" scope="row">
              {key}
            </TableCell>
            {symbols.map((symbol) => (
              <TableCell key={symbol} align="right">
                {fmtUnknown(symbolStats[symbol][key])}
              </TableCell>
            ))}
            <TableCell>{fmtUnknown(keyTotals[i])}</TableCell>
          </TableRow>
        ))
    );
  }

  return (
    <>
      {onClose && <Button onClick={onClose}>&lt; Back</Button>}

      <Paper>
        <pre>{JSON.stringify(config, null, 4)}</pre>
      </Paper>

      <TableContainer component={Paper}>
        <Table size="small" aria-label="a dense table">
          <TableHead>
            <TableRow>
              <TableCell>{title}</TableCell>
              {args.trainingSymbols.map((symbol) => (
                <TableCell key={symbol} align="right">
                  {symbol}
                </TableCell>
              ))}
              {args.validationSymbols.map((symbol) => (
                <TableCell key={symbol} align="right">
                  {symbol} (v)
                </TableCell>
              ))}
              <TableCell>total</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>{renderStats()}</TableBody>
        </Table>
      </TableContainer>

      {symbolCandles !== null &&
        args.trainingSymbols.map((symbol) => (
          <Chart
            key={symbol}
            symbol={symbol}
            candles={symbolCandles[symbol]}
            stats={symbolStats[symbol]}
          />
        ))}

      {symbolCandles !== null &&
        args.validationSymbols.map((symbol) => (
          <Chart
            key={symbol}
            symbol={`${symbol} (v)`}
            candles={symbolCandles[symbol]}
            stats={symbolStats[symbol]}
          />
        ))}
    </>
  );
}

function fmtUnknown(value) {
  if (typeof value === 'number' && !Number.isInteger(value)) {
    return value.toFixed(8);
  }
  return value;
}
