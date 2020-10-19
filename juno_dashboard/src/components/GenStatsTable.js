import React from 'react';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';
import Button from '@material-ui/core/Button';

function* range(stop) {
    let i = 0;
    while (i < stop) {
        yield i++;
    }
}

export default function GenStatsTable(props) {
    const { args, gen } = props;
    const totalSymbols = args.trainingSymbols.length + args.validationSymbols.length;

    return (
        <>
            <Button onClick={props.onClose}>Back</Button>

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
                    {gen.symbolStats.length && Object.keys(gen.symbolStats[0]).map(key => (
                        <TableRow key={key}>
                            <TableCell component="th" scope="row">{key}</TableCell>
                            {Array.from(range(totalSymbols), (i) => (
                                <TableCell key={i} align="right">
                                    {gen.symbolStats[i][key]}
                                </TableCell>
                            ))}
                        </TableRow>
                    ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </>
    );
}
