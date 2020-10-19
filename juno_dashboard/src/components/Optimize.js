import React, { useEffect, useState } from 'react';
import Container from '@material-ui/core/Container';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableContainer from '@material-ui/core/TableContainer';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import Paper from '@material-ui/core/Paper';

async function fetchJson(method, url, body) {
    const response = await fetch(url, {
        method,
        headers: {
            'content-type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    return await response.json();
}

export default function Optimize() {
    const trainingSymbols = ["eth-btc", "ltc-btc", "xrp-btc", "xmr-btc"];
    const validationSymbols = ["ada-btc"];
    const [gens, setGens] = useState([]);
    useEffect(() => {
        (async () => setGens(await fetchJson('POST', '/optimize', {
            "exchange": "binance",
            "interval": "1d",
            "start": "2017-12-08",
            "end": "2020-09-30",
            "quote": 1.0,
            "training_symbols": trainingSymbols,
            "validation_symbols": validationSymbols,
        })))();
    }, [trainingSymbols, validationSymbols]);

    return (
        <Container>
            <TableContainer component={Paper}>
                <Table size="small" aria-label="a dense table">
                    <TableHead>
                        <TableRow>
                            <TableCell>gen</TableCell>
                            {/* {trainingSymbols.map(symbol => (
                                <TableCell align="right">{symbol}</TableCell>
                            ))}
                            {validationSymbols.map(symbol => (
                                <TableCell align="right">{symbol} (v)</TableCell>
                            ))} */}
                            <TableCell align="right">fitness</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                    {gens.map((gen, i) => (
                        <TableRow key={i}>
                            <TableCell component="th" scope="row">{i}</TableCell>
                            <TableCell align="right">{gen.fitness}</TableCell>
                        </TableRow>
                    ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Container>
    );
}
