import React, { useEffect, useRef } from 'react';
import { PriceScaleMode, createChart } from 'lightweight-charts';

export default function Chart({ symbol, candles, summary }) {
    const container = useRef(null);
    const tooltip = useRef(null);

    const tooltipWidthPx = 96;
    const tooltipStyle = {
        width: `${tooltipWidthPx}px`,
        height: '80px',
        position: 'absolute',
        display: 'none',
        padding: '8px',
        zIndex: 1000,
    };

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
                // TODO: Use a color from palette.
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
            .flatMap((pos, i) => {
                const shape = pos.type === 'Long' ? 'arrowUp' : 'arrowDown';
                const id = i + 1;
                return [
                    {
                        // We keep the id 1-based to distinguish between open and pos (neg and pos).
                        id: -id,
                        time: pos.time,
                        position: 'aboveBar',
                        shape,
                        color: 'blue',
                    },
                    {
                        id: +id,
                        time: pos.closeTime,
                        position: 'aboveBar',
                        shape,
                        color: 'orange',
                    },
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
        const volume = candles
            .reduce(([prevClose, volume], candle) => {
                const color = candle.close >= prevClose ? '#26a69a80' : '#ef535080';
                volume.push({
                    time: candle.time,
                    value: candle.volume,
                    color,
                });
                return [candle.close, volume];
            }, [0, []])[1];
            // .map(candle => ({
            //     time: candle.time,
            //     value: candle.volume,
            //     // Set colors similar to:
            //     // https://jsfiddle.net/TradingView/cnbamtuh/
            //     // color: 
            // }));
        volumeSeries.setData(volume);
        function onCrosshairMove({ hoveredMarkerId, point }) {
            if (typeof hoveredMarkerId === 'number') {
                const x = point.x - tooltipWidthPx / 2;
                const y = point.y;

                tooltip.current.style.display = 'block';
                tooltip.current.style.left = `${x}px`;
                tooltip.current.style.top = `${y}px`;
                if (hoveredMarkerId < 0) { // open
                    const pos = summary.positions[-hoveredMarkerId - 1];

                } else { // close
                    const pos = summary.positions[hoveredMarkerId - 1];
                }
                console.log(tooltip.current.style.display);
            } else {
                tooltip.current.style.display = 'none';
            }
        }
        chart.subscribeCrosshairMove(onCrosshairMove);
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
        return () => chart.unsubscribeCrosshairMove(onCrosshairMove);
    }, [symbol, candles, summary]);

    // useEffect(() => {
    //     candlestickSeries.update(lastCandle);
    // }, [lastCandle]);

    return (
        <>
            <div ref={container} />
            <div ref={tooltip} style={tooltipStyle} />
        </>
    );
}
