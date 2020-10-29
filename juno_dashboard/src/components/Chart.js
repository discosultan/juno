import React, { useEffect, useRef } from 'react';
import { PriceScaleMode, createChart } from 'lightweight-charts';

export default function Chart({ symbol, candles, summary }) {
    const container = useRef(null);

    useEffect(() => {
        container.current.innerHTML = '';
        // TODO: Theme with Material UI palette colors.
        const chart = createChart(container.current, {
            // width: 1000,
            height: 320,
            rightPriceScale: {
                mode: PriceScaleMode.Logarithmic,
            },
            watermark: {
                visible: true,
                text: symbol,
                vertAlign: 'top',
                horzAlign: 'left',
                color: 'rgba(11, 94, 29, 0.4)',
                fontSize: 20,
            },
        });
        const candleSeries = chart.addCandlestickSeries({
            // TODO: Calculate dynamically.
            priceFormat: {
                type: 'price',
                precision: 8,
                minMove: 0.0000001,
            },
        });
        candleSeries.setData(candles);
        const markers = summary.positions
            .flatMap(pos => {
                const shape = pos.type === 'Long' ? 'arrowUp' : 'arrowDown';
                return [
                    {
                        time: pos.time,
                        position: 'aboveBar',
                        shape,
                        color: 'blue',
                    },
                    {
                        time: pos.closeTime,
                        position: 'aboveBar',
                        shape,
                        color: 'orange',
                    }
                ];
            });
        candleSeries.setMarkers(markers);
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '',
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });
        const volume = candles.map(candle => ({
            time: candle.time,
            value: candle.volume,
            // Set colors similar to:
            // https://jsfiddle.net/TradingView/cnbamtuh/
            // color: 
        }));
        volumeSeries.setData(volume);
        // const lineSeries = chart.addLineSeries();
        // lineSeries.setData(candles.map(candle => ({
        //     time: candle.time,
        //     value: candle.close,
        // })));

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
    }, [symbol, candles, summary]);

    // useEffect(() => {
    //     candlestickSeries.update(lastCandle);
    // }, [lastCandle]);

    return <div ref={container} />;
}
