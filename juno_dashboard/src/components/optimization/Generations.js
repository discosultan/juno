import React from 'react';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';
import { makeStyles } from '@material-ui/core';

const useStyles = makeStyles((_theme) => ({
  row: {
    cursor: 'pointer',
  },
}));

export default function Generations({ info, onSelect }) {
  const { args, gens } = info;
  const classes = useStyles();
  const symbols = args.trainingSymbols.concat(args.validationSymbols);

  return (
    <>
      <Paper>
        <pre>{JSON.stringify(args, null, 4)}</pre>
      </Paper>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="a dense table">
          <TableHead>
            <TableRow>
              <TableCell>gen</TableCell>
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
              <TableCell align="right">fitness</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {gens.map((gen) => (
              <TableRow
                key={gen.nr}
                hover
                className={classes.row}
                onClick={() => onSelect(info, gen)}
              >
                <TableCell component="th" scope="row">
                  {gen.nr}
                </TableCell>
                {symbols.map((symbol) => (
                  <TableCell key={symbol} align="right">
                    {gen.symbolStats[symbol].sharpeRatio}
                  </TableCell>
                ))}
                <TableCell align="right">{gen.ind.fitness}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
