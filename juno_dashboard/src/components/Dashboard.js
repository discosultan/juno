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
    const [gensInfo, setGensInfo] = useState(null);
    const [selectedGenInfo, setSelectedGenInfo] = useState(null);

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
        setGensInfo({
            args,
            symbolCandles,
            gens,
        });
        setSelectedGenInfo(null);
    }

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
                {selectedGenInfo ?
                    <Generation
                        info={selectedGenInfo}
                        onClose={() => setSelectedGenInfo(null)}
                    />
                : gensInfo &&
                    <Generations
                        info={gensInfo}
                        onSelect={(gensInfo, gen) => setSelectedGenInfo({
                            args: gensInfo.args,
                            symbolCandles: gensInfo.symbolCandles,
                            gen,
                        })}
                    />
                }
            </main>
        </>
    );
}
