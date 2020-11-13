import React, { useState } from 'react';
import Box from '@material-ui/core/Box';
import Divider from '@material-ui/core/Divider';
import Drawer from '@material-ui/core/Drawer';
import Toolbar from '@material-ui/core/Toolbar';
import { makeStyles } from '@material-ui/core/styles';
import ControlPanel from './ControlPanel';
import History from './History';
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
    },
}));

export default function Dashboard() {
    const classes = useStyles();
    const [gensInfo, setGensInfo] = useState(null);
    const [selectedGenInfo, setSelectedGenInfo] = useState(null);
    // TODO: It would be nice to store the state in local storage. However, it is limited to only
    // 5MB. If we didn't store candle data with it, we could hold more.
    const [history, setHistory] = useState([]);

    function processNewGensInfo(gensInfo) {
        setGensInfo(gensInfo);
        setSelectedGenInfo(null);
    }

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
        const gensInfo = {
            args,
            symbolCandles,
            gens,
        };

        const historyItem = {
            time: new Date().toISOString(),
            gensInfo,
        };
        if (history.length === 10) {
            setHistory([historyItem, ...history.slice(0, history.length - 1)]);
        } else {
            setHistory([historyItem, ...history]);
        }

        processNewGensInfo(gensInfo);
    }

    return (
        <>
            <Drawer
                variant="permanent"
                anchor="left"
                className={classes.drawer}
                classes={{ paper: classes.drawer }}
            >
                {/* Dummy toolbar to add toolbar's worth of space to the top. Otherwise the
                component will run under app bar. Same for the main section below. */}
                <Toolbar />
                <Box p={1}>
                    <History
                        gensInfo={gensInfo}
                        history={history}
                        onChange={gensInfo => processNewGensInfo(gensInfo)} />
                </Box>
                <Divider />
                <Box p={1}>
                    <ControlPanel onOptimize={optimize} />
                </Box>
            </Drawer>
            <main className={classes.main}>
                <Toolbar />
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
