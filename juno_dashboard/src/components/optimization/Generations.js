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

export default function Generations({ value, onSelect }) {
  const { args, gens } = value;
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
            {/* We reverse gens to show the latest on top */}
            {gens
              .slice(0)
              .reverse()
              .map((gen, i) =>
                gen.hallOfFame.map((ind, j) => (
                  <TableRow
                    key={i * args.hallOfFameSize + j}
                    hover
                    className={classes.row}
                    onClick={() => onSelect(value, gen, ind)}
                  >
                    <TableCell component="th" scope="row">
                      {gen.nr}
                    </TableCell>
                    {symbols.map((symbol) => (
                      <TableCell key={symbol} align="right">
                        {getEvaluationStat(
                          ind.symbolStats[symbol],
                          args.evaluationStatistic,
                        ).toFixed(8)}
                      </TableCell>
                    ))}
                    <TableCell align="right">{ind.ind.fitness.toFixed(8)}</TableCell>
                  </TableRow>
                )),
              )}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}

function getEvaluationStat(stats, evaluationStatistic) {
  evaluationStatistic = evaluationStatistic.charAt(0).toLowerCase() + evaluationStatistic.slice(1);
  let result = stats.core[evaluationStatistic];
  if (result === undefined) {
    result = stats.extended[evaluationStatistic];
  }
  return result;
}
