import React from 'react';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';
import Button from '@material-ui/core/Button';
import Chart from './Chart';

export default function Generation({ args, gen, symbolCandles, onClose }) {
    const symbols = args.trainingSymbols.concat(args.validationSymbols);
    const stats = Object.values(gen.symbolStats);

    return (
        <>
            <Button onClick={onClose}>Back</Button>

            <Paper>
                <pre>
                    {JSON.stringify(gen.ind.chromosome, null, 4)}
                </pre>
            </Paper>

            <TableContainer component={Paper}>
                <Table size="small" aria-label="a dense table">
                    <TableHead>
                        <TableRow>
                            <TableCell>gen {gen.nr}</TableCell>
                            {args.trainingSymbols.map(symbol => (
                                <TableCell key={symbol} align="right">{symbol}</TableCell>
                            ))}
                            {args.validationSymbols.map(symbol => (
                                <TableCell key={symbol} align="right">{symbol} (v)</TableCell>
                            ))}
                        </TableRow>
                    </TableHead>
                    <TableBody>
                    {stats.length && Object.keys(stats[0]).map(key => (
                        <TableRow key={key}>
                            <TableCell component="th" scope="row">{key}</TableCell>
                            {symbols.map(symbol => (
                                <TableCell key={symbol} align="right">
                                    {gen.symbolStats[symbol][key]}
                                </TableCell>
                            ))}
                        </TableRow>
                    ))}
                    </TableBody>
                </Table>
            </TableContainer>

            {args.trainingSymbols.map(symbol => (
                <Chart
                    key={symbol}
                    symbol={symbol}
                    candles={symbolCandles[symbol]}
                    summary={gen.symbolSummaries[symbol]} />
            ))}

            {args.validationSymbols.map(symbol => (
                <Chart
                    key={symbol}
                    symbol={`${symbol} (v)`}
                    candles={symbolCandles[symbol]}
                    summary={gen.symbolSummaries[symbol]} />
            ))}
        </>
    );
}
