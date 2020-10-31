import React, { useState } from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import Box from '@material-ui/core/Box';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import { KeyboardDatePicker } from '@material-ui/pickers';

const Symbols = ['eth-btc', 'ltc-btc', 'xrp-btc', 'xmr-btc', 'ada-btc'];

function fmtTimestamp(date) {
    return date.toISOString();
}

export default function ControlPanel({ onOptimize }) {
    const [strategy, setStrategy] = useState('fourweekrule');
    const [exchange, setExchange] = useState('binance');
    const [trainingSymbols, setTrainingSymbols] = useState(
        ["eth-btc", "ltc-btc", "xrp-btc", "xmr-btc"]
    );
    const [validationSymbols, setValidationSymbols] = useState(['ada-btc']);
    const [interval, setInterval] = useState('1d');
    const [start, setStart] = useState('2017-12-08');
    const [end, setEnd] = useState('2020-09-30');
    const [generations, setGenerations] = useState(32);
    const [populationSize, setPopulationSize] = useState(32);

    return (
        <Box p={1}>
            <form noValidate autoComplete="off">
                <TextField
                    id="strategy"
                    label="Strategy"
                    fullWidth
                    select
                    value={strategy}
                    onChange={e => setStrategy(e.target.value)}
                >
                    <MenuItem value={'fourweekrule'}>Four Week Rule</MenuItem>
                </TextField>

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
                     {Symbols.map(symbol =>
                         <MenuItem key={symbol} value={symbol}>{symbol}</MenuItem>
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
                     {Symbols.map(symbol =>
                         <MenuItem key={symbol} value={symbol}>{symbol}</MenuItem>
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
                    onChange={d => setStart(fmtTimestamp(d))}
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
                    onChange={d => setEnd(fmtTimestamp(d))}
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
                    value={populationSize}
                    onChange={e => setPopulationSize(e.target.valueAsNumber)}
                />

                <br />
                <br />
                <Button fullWidth variant="contained" onClick={() => onOptimize({
                    strategy,
                    exchange,
                    trainingSymbols,
                    validationSymbols,
                    interval,
                    start,
                    end,
                    quote: 1.0,
                    populationSize,
                    generations,
                })}>
                    Optimize
                </Button>
            </form>
        </Box>
    );
}
