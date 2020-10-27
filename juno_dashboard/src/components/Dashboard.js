import React, { useEffect, useState } from 'react';
import Container from '@material-ui/core/Container';
import Generations from './Generations';
import Generation from './Generation';

async function fetchJson(method, url, body) {
    const response = await fetch(url, {
        method,
        headers: {
            'content-type': 'application/json',
        },
        body: JSON.stringify(body, camelToSnakeReplacer),
    });
    const text = await response.text();
    return JSON.parse(text, snakeToCamelReviver);
}

function camelToSnakeReplacer(_key, value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        const replacement = {};
        for (const [objKey, objValue] of Object.entries(value)) {
            replacement[objKey.replace(/([A-Z])/g, "_$1").toLowerCase()] = objValue;
        }
        return replacement;
    }
    return value;
}

function snakeToCamelReviver(_key, value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        const replacement = {};
        for (const [objKey, objValue] of Object.entries(value)) {
            replacement[objKey.replace(/(_\w)/g, k => k[1].toUpperCase())] = objValue;
        }
        return replacement;
    }
    return value;
}

const args = {
    populationSize: 32,
    generations: 32,

    exchange: "binance",
    interval: "1d",
    start: "2017-12-08",
    end: "2020-09-30",
    quote: 1.0,
    trainingSymbols: ["eth-btc", "ltc-btc", "xrp-btc", "xmr-btc"],

    validationSymbols: ["ada-btc"],
};

export default function Dashboard() {
    const [gens, setGens] = useState([]);
    const [selectedGen, setSelectedGen] = useState(null);
    useEffect(() => {
        (async () => setGens(await fetchJson('POST', '/optimize', args)))()
    }, []);

    return (
        <Container>
            {selectedGen ? (
                <Generation args={args} gen={selectedGen} onClose={() => setSelectedGen(null)} />
            ) : (
                    <Generations args={args} gens={gens} onSelect={setSelectedGen} />
                )}
        </Container>
    );
}
