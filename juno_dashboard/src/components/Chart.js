import React, { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';

export default function Chart({ symbol, candles }) {
    const container = useRef(null);

    // let chart;
    // let candlestickSeries;

    useEffect(() => {
        container.current.innerHTML = '';
        console.log(symbol);
        const chart = createChart(container.current, {
            // width: 1000,
            height: 320,
            watermark: {
                visible: true,
                text: symbol,
                vertAlign: 'top',
                horzAlign: 'left',
                color: 'rgba(11, 94, 29, 0.4)',
                fontSize: 20,
            },
        });
        const candleSeries = chart.addCandlestickSeries();
        candleSeries.setData(candles);
        // const lineSeries = chart.addLineSeries();
        // lineSeries.setData(candles.map(candle => ({
        //     time: candle.time,
        //     value: candle.close,
        // })));

        //  [
        //     { time: '2019-04-12', value: 96.63 },
        //     { time: '2019-04-13', value: 76.64 },
        //     { time: '2019-04-14', value: 81.89 },
        //     { time: '2019-04-15', value: 74.43 },
        //     { time: '2019-04-16', value: 80.01 },
        //     { time: '2019-04-17', value: 96.63 },
        //     { time: '2019-04-18', value: 76.64 },
        //     { time: '2019-04-19', value: 81.89 },
        //     { time: '2019-04-20', value: 74.43 },
        // ]);
        // chart.applyOptions({
        //     timeScale: {
        //         rightOffset: 45,
        //         barSpacing: 15,
        //         lockVisibleTimeRangeOnResize: true,
        //         rightBarStaysOnScroll: true,
        //     },
        //     priceScale: {
        //         position: 'right',
        //         // mode: 1,
        //         autoScale: false,
        //         // invertScale: true,
        //         alignLabels: true,
        //         borderVisible: false,
        //         borderColor: '#555ffd',
        //         scaleMargins: {
        //             top: 0.65,
        //             bottom: 0.25,
        //         },
        //         crosshair: {
        //             vertLine: {
        //                 color: '#6A5ACD',
        //                 width: 0.5,
        //                 style: 1,
        //                 visible: true,
        //                 labelVisible: false,
        //             },
        //             horzLine: {
        //                 color: '#6A5ACD',
        //                 width: 0.5,
        //                 style: 0,
        //                 visible: true,
        //                 labelVisible: true,
        //             },
        //             mode: 1,
        //         },
        //         grid: {
        //             vertLines: {
        //                 color: 'rgba(70, 130, 180, 0.5)',
        //                 style: 1,
        //                 visible: true,
        //             },
        //             horzLines: {
        //                 color: 'rgba(70, 130, 180, 0.5)',
        //                 style: 1,
        //                 visible: true,
        //             },
        //         },

        //     },
        // });
        // candlestickSeries = chart.addCandlestickSeries({
        //     upColor: '#0B6623',
        //     downColor: '#FF6347',
        //     borderVisible: false,
        //     wickVisible: true,
        //     borderColor: '#000000',
        //     wickColor: '#000000',
        //     borderUpColor: '#4682B4',
        //     borderDownColor: '#A52A2A',
        //     wickUpColor: "#4682B4",
        //     wickDownColor: "#A52A2A",
        // });
    }, [symbol, candles]);

    // useEffect(() => {
    //     candlestickSeries.update(lastCandle);
    // }, [lastCandle]);

    return <div ref={container} />;
}