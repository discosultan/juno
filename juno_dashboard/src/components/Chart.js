import React, { useEffect, useRef, useState } from 'react';
import { PriceScaleMode, createChart } from 'lightweight-charts';
import Typography from '@material-ui/core/Typography';
import { useTheme } from '@material-ui/core/styles';
// import { clamp } from '../math';

function fmtPct(value) {
    return value.toLocaleString(undefined, { style: 'percent', minimumFractionDigits: 2 });
}

export default function Chart({ symbol, candles, summary }) {
    const { palette } = useTheme();
    console.log(palette);
    const container = useRef(null);
    const tooltip = useRef(null);

    // The width and height also include border size.
    const halfTooltipWidth = 64;
    const tooltipHeight = 118;
    const [tooltipStyle, setTooltipStyle] = useState({
        width: `${halfTooltipWidth * 2}px`,
        height: `${tooltipHeight}px`,
        boxSizing: 'border-box',
        position: 'absolute',
        display: 'none',
        padding: '8px',
        zIndex: 1000,
        border: '1px solid',
        backgroundColor: palette.background.paper,
        whiteSpace: 'pre-line',
    });
    const [tooltipText, setTooltipText] = useState('');

    useEffect(() => {
        container.current.innerHTML = '';
        // TODO: Theme with Material UI palette colors.
        const chart = createChart(container.current, {
            // width: 1000,
            height: 320,
            layout: {
                backgroundColor: palette.background.paper,
                textColor: palette.text.primary,
            },
            rightPriceScale: {
                mode: PriceScaleMode.Logarithmic,
            },
            watermark: {
                visible: true,
                text: symbol,
                vertAlign: 'top',
                horzAlign: 'left',
                color: palette.text.primary,
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
                        color: palette.info[palette.type],
                    },
                    {
                        id: +id,
                        time: pos.closeTime,
                        position: 'aboveBar',
                        shape,
                        color: palette.warning[palette.type],
                        // text: `profit ${pos.profit}\nroi ${pos.roi}\naroi ${pos.annualizedRoi}`,
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
        volumeSeries.setData(volume);
        function onCrosshairMove(event) {
            const { hoveredMarkerId, point } = event;
            if (typeof hoveredMarkerId === 'number') {
                const yOffset = 5;
                const x = Math.round(point.x) - halfTooltipWidth;
                const y = Math.round(point.y) + yOffset;
                // const x = clamp(
                //     Math.round(point.x) - halfTooltipWidth,
                //     0,
                //     container.current.clientWidth,
                // );
                // const y = clamp(
                //     Math.round(point.y) + yOffset,
                //     0,
                //     container.current.clientHeight - tooltipHeight,
                // );

                const newStyle = {
                    display: 'block',
                    left: `${x}px`,
                    top: `${y}px`,
                    borderColor: '#26a69a',
                };
                if (hoveredMarkerId < 0) { // open
                    const pos = summary.positions[-hoveredMarkerId - 1];
                    setTooltipText(`cost: ${pos.cost}`);
                } else { // close
                    const pos = summary.positions[hoveredMarkerId - 1];
                    if (pos.roi < 0) {
                        newStyle.borderColor = '#ef5350';
                    }
                    setTooltipText(''
                        + `gain: ${pos.gain.toFixed(8)}\n`
                        + `profit: ${pos.profit.toFixed(8)}\n`
                        + `duration: ${pos.duration}\n`
                        + `roi: ${fmtPct(pos.roi)}\n`
                        + `aroi: ${fmtPct(pos.annualizedRoi)}`
                    );
                }
                setTooltipStyle(style => ({...style, ...newStyle}));
            } else if (tooltip.current.style.display !== 'none') {
                setTooltipStyle(style => ({...style, display: 'none'}));
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
    }, [symbol, candles, summary, palette]);

    return (
        <div style={{ position: 'relative' }}>
            <div ref={container} />
            <div ref={tooltip} style={tooltipStyle}>
                <Typography variant="caption">{tooltipText}</Typography>
            </div>
        </div>
    );
}
