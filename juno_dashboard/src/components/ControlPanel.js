import React, { useState } from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import Box from '@material-ui/core/Box';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import { KeyboardDatePicker } from '@material-ui/pickers';

const SYMBOLS = ['eth-btc', 'ltc-btc', 'xrp-btc', 'xmr-btc', 'ada-btc'];

export default function ControlPanel() {
    const [exchange, setExchange] = useState('binance');
    const [trainingSymbols, setTrainingSymbols] = useState(['eth-btc']);
    const [validationSymbols, setValidationSymbols] = useState(['ada-btc']);
    const [interval, setInterval] = useState('1d');
    const [start, setStart] = useState('2017-12-08');
    const [end, setEnd] = useState('2020-09-30');
    const [generations, setGenerations] = useState(32);
    const [population, setPopulation] = useState(32);

    return (
        <Box p={1}>
            <form noValidate autoComplete="off">
                <TextField
                    id="exchange"
                    fullWidth
                    select
                    label="Exchange"
                    value={exchange}
                    onChange={e => setExchange(e.target.value)}
                >
                    <MenuItem value={'binance'}>Binance</MenuItem>
                </TextField>

                <TextField
                    id="training-symbols"
                    label="Training Symbols"
                    fullWidth
                    select
                    SelectProps={{
                        multiple: true,
                        value: trainingSymbols,
                        onChange: e => setTrainingSymbols(e.target.value),
                    }}
                >
                     {SYMBOLS.map(symbol =>
                         <MenuItem value={symbol}>{symbol}</MenuItem>
                     )}
                </TextField>
                <TextField
                    id="validation-symbols"
                    label="Validation Symbols"
                    fullWidth
                    select
                    SelectProps={{
                        multiple: true,
                        value: validationSymbols,
                        onChange: e => setValidationSymbols(e.target.value),
                    }}
                >
                     {SYMBOLS.map(symbol =>
                         <MenuItem value={symbol}>{symbol}</MenuItem>
                     )}
                </TextField>

                <TextField
                    id="interval"
                    fullWidth
                    select
                    label="Interval"
                    value={interval}
                    onChange={e => setInterval(e.target.value)}
                >
                    <MenuItem value={'1m'}>1m</MenuItem>
                    <MenuItem value={'5m'}>5m</MenuItem>
                    <MenuItem value={'15m'}>15m</MenuItem>
                    <MenuItem value={'30m'}>30m</MenuItem>
                    <MenuItem value={'1h'}>1h</MenuItem>
                    <MenuItem value={'2h'}>2h</MenuItem>
                    <MenuItem value={'4h'}>4h</MenuItem>
                    <MenuItem value={'6h'}>6h</MenuItem>
                    <MenuItem value={'8h'}>8h</MenuItem>
                    <MenuItem value={'12h'}>12h</MenuItem>
                    <MenuItem value={'1d'}>1d</MenuItem>
                </TextField>

                <KeyboardDatePicker
                    disableToolbar
                    variant="inline"
                    format="yyyy-MM-dd"
                    id="start"
                    label="Start"
                    fullWidth
                    autoOk={true}
                    value={start}
                    onChange={setStart}
                    KeyboardButtonProps={{
                        'aria-label': 'change date',
                    }}
                />
                <KeyboardDatePicker
                    disableToolbar
                    variant="inline"
                    format="yyyy-MM-dd"
                    id="end"
                    label="End"
                    fullWidth
                    autoOk={true}
                    value={end}
                    onChange={setEnd}
                    KeyboardButtonProps={{
                        'aria-label': 'change date',
                    }}
                />

                <TextField
                    id="generations"
                    fullWidth
                    label="Number Of Generations"
                    type="number"
                    value={generations}
                    onChange={e => setGenerations(e.target.valueAsNumber)}
                />
                <TextField
                    id="population"
                    fullWidth
                    label="Population Size"
                    type="number"
                    value={population}
                    onChange={e => setPopulation(e.target.valueAsNumber)}
                />

                <br />
                <br />
                <Button fullWidth variant="contained">Optimize</Button>
            </form>
        </Box>
    );
}
