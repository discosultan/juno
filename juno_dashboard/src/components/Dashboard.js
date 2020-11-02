import React, { useState } from 'react';
import Drawer from '@material-ui/core/Drawer';
import { makeStyles } from '@material-ui/core/styles';
import ControlPanel from './ControlPanel';
import Generations from './Generations';
import Generation from './Generation';
import { fetchJson } from '../fetch';

const drawerWidth = '20%';
const useStyles = makeStyles((_theme) => ({
    drawer: {
      width: drawerWidth,
    },
    main: {
        marginLeft: drawerWidth,
    }
}));

export default function Dashboard() {
    const classes = useStyles();
    const [args, setArgs] = useState();
    const [gens, setGens] = useState([]);
    const [selectedGen, setSelectedGen] = useState(null);
    const [symbolCandles, setSymbolCandles] = useState({});

    async function optimize(args) {
        const [gens, symbolCandles] = await Promise.all([
            fetchJson('POST', '/optimize', args),
            fetchJson('POST', '/candles', {
                exchange: args.exchange,
                interval: args.interval,
                start: args.start,
                end: args.end,
                symbols: args.trainingSymbols.concat(args.validationSymbols),
            }),
        ]);
        setArgs(args);
        setGens(gens);
        setSymbolCandles(symbolCandles);
        setSelectedGen(null);
    }

    // useEffect(() => {
    //     (async () => {
    //         const [gens, symbolCandles] = await Promise.all([
    //             fetchJson('POST', '/optimize', args),
    //             fetchJson('POST', '/candles', {
    //                 exchange: args.exchange,
    //                 interval: args.interval,
    //                 start: args.start,
    //                 end: args.end,
    //                 symbols: args.trainingSymbols.concat(args.validationSymbols),
    //             }),
    //         ]);
    //         setGens(gens);
    //         setSymbolCandles(symbolCandles);
    //     })();
    // }, []);

    return (
        <>
            <Drawer 
                variant="permanent"
                anchor="left"
                className={classes.drawer}
                classes={{ paper: classes.drawer }}
            >
                <ControlPanel onOptimize={optimize} />
            </Drawer>
            <main className={classes.main}>
                {args && (
                    selectedGen ?
                        <Generation
                            args={args}
                            gen={selectedGen}
                            symbolCandles={symbolCandles}
                            onClose={() => setSelectedGen(null)} />
                    :
                        <Generations
                            args={args}
                            gens={gens}
                            onSelect={setSelectedGen} />
                )}
            </main>
        </>
    );
}
