import React from 'react';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';
import { makeStyles } from '@material-ui/core';

const useStyles = makeStyles(_theme => ({
    row: {
        'cursor': 'pointer'
    },
}));

export default function GensTable(props) {
    const classes = useStyles();

    return (
        <TableContainer component={Paper}>
            <Table size="small" aria-label="a dense table">
                <TableHead>
                    <TableRow>
                        <TableCell>gen</TableCell>
                        {props.args.trainingSymbols.map(symbol => (
                            <TableCell key={symbol} align="right">{symbol}</TableCell>
                        ))}
                        {props.args.validationSymbols.map(symbol => (
                            <TableCell key={symbol} align="right">{symbol} (v)</TableCell>
                        ))}
                        <TableCell align="right">fitness</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {props.gens.map(gen => (
                        <TableRow
                            key={gen.nr}
                            hover
                            className={classes.row}
                            onClick={() => props.onSelect(gen)}
                        >
                            <TableCell component="th" scope="row">{gen.nr}</TableCell>
                            {gen.symbolStats.map((stats, i) => (
                                <TableCell key={i} align="right">{stats.sharpeRatio}</TableCell>
                            ))}
                            <TableCell align="right">{gen.ind.fitness}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </TableContainer>
    );
}
