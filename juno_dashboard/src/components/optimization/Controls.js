import React from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import Typography from '@material-ui/core/Typography';
import useLocalStorageStateImpl from 'use-local-storage-state';
import DatePicker from '../DatePicker';
import { Strategies, Symbols, Intervals } from '../info';

function useLocalStorageState(key, defaultValue) {
    return useLocalStorageStateImpl(`optimization_controls_${key}`, defaultValue);
}

export default function ControlPanel({ onOptimize }) {
    const [strategy, setStrategy] = useLocalStorageState('strategy', 'fourweekrule');
    const [exchange, setExchange] = useLocalStorageState('exchange', 'binance');
    const [trainingSymbols, setTrainingSymbols] = useLocalStorageState(
        'trainingSymbols', ['eth-btc', 'ltc-btc', 'xrp-btc', 'xmr-btc']
    );
    const [validationSymbols, setValidationSymbols] = useLocalStorageState(
        'validationSymbols', ['ada-btc']
    );
    const [interval, setInterval] = useLocalStorageState('interval', '1d');
    const [start, setStart] = useLocalStorageState('start', '2017-12-08');
    const [end, setEnd] = useLocalStorageState('end', '2020-11-01');
    const [generations, setGenerations] = useLocalStorageState('generations', 32);
    const [populationSize, setPopulationSize] = useLocalStorageState('populationSize', 32);

    return (
        <form noValidate autoComplete="off">
            <Typography variant="h6" gutterBottom>Configure Optimization Args</Typography>

            <TextField
                id="strategy"
                label="Strategy"
                fullWidth
                select
                value={strategy}
                onChange={e => setStrategy(e.target.value)}
            >
                {Strategies.map(strategy =>
                    <MenuItem key={strategy} value={strategy}>{strategy}</MenuItem>
                )}
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
                {Intervals.map(interval =>
                    <MenuItem key={interval} value={interval}>{interval}</MenuItem>
                )}
            </TextField>

            <DatePicker
                label="Start"
                value={start}
                onChange={e => setStart(e.target.value)}
            />
            <DatePicker
                label="End"
                value={end}
                onChange={e => setEnd(e.target.value)}
            />

            <TextField
                id="generations"
                fullWidth
                label="Number Of Generations"
                type="number"
                inputProps={{ min: 0 }}
                value={generations}
                onChange={e => setGenerations(e.target.valueAsNumber)}
            />
            <TextField
                id="population"
                fullWidth
                label="Population Size"
                type="number"
                inputProps={{ min: 2 }}
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
    );
}
