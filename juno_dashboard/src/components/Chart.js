import React, { useEffect, useRef, useState } from 'react';
import { PriceScaleMode, createChart } from 'lightweight-charts';
import Box from '@material-ui/core/Box';
import Typography from '@material-ui/core/Typography';
import { useTheme } from '@material-ui/core/styles';
import useResizeObserver from 'use-resize-observer';

function fmtPct(value) {
  return value.toLocaleString(undefined, { style: 'percent', minimumFractionDigits: 2 });
}

function timestamp(value) {
  return new Date(value).getTime() / 1000;
}

export default function Chart({ symbol, candles, summary }) {
  const { palette } = useTheme();
  const chartRef = useRef(null);
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);

  const [tooltipStyle, setTooltipStyle] = useState({
    position: 'absolute',
    display: 'none',
    padding: '8px',
    zIndex: 1000,
    border: '1px solid',
    backgroundColor: palette.background.paper,
    whiteSpace: 'pre-line',
  });
  const [tooltipText, setTooltipText] = useState('');

  useResizeObserver({
    ref: containerRef,
    onResize: ({ width }) => {
      chartRef.current && chartRef.current.applyOptions({ width });
    },
  });

  useEffect(() => {
    // Delete existing chart from container if any.
    chartRef.current && chartRef.current.remove();

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 360,
      layout: {
        backgroundColor: palette.background.paper,
        textColor: palette.text.primary,
      },
      localization: {
        dateFormat: 'yyyy-MM-dd',
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      leftPriceScale: {
        visible: true,
        mode: PriceScaleMode.Logarithmic,
      },
      rightPriceScale: {
        visible: true,
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
    chartRef.current = chart;

    // Candles.
    const candleSeries = chart.addCandlestickSeries({
      // TODO: Calculate dynamically.
      priceFormat: {
        type: 'price',
        precision: 8,
        minMove: 0.0000001,
      },
    });
    candleSeries.setData(
      candles.map((candle) => ({
        time: timestamp(candle.time),
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
      })),
    );
    const markers = summary.positions.flatMap((pos, i) => {
      const shape = pos.type === 'Long' ? 'arrowUp' : 'arrowDown';
      const id = i + 1;
      return [
        {
          // We keep the id 1-based to distinguish between open and pos (neg and pos).
          id: -id,
          time: timestamp(pos.time),
          position: 'aboveBar',
          shape,
          color: palette.info[palette.type],
        },
        {
          id: +id,
          time: timestamp(pos.closeTime),
          position: 'aboveBar',
          shape,
          color: palette.warning[palette.type],
        },
      ];
    });
    candleSeries.setMarkers(markers);

    // Volume.
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
    const volume = candles.reduce(
      ([prevClose, volume], candle) => {
        const color = candle.close >= prevClose ? '#26a69a80' : '#ef535080';
        volume.push({
          time: timestamp(candle.time),
          value: candle.volume,
          color,
        });
        return [candle.close, volume];
      },
      [0, []],
    )[1];
    volumeSeries.setData(volume);

    // Tooltip on markers.
    function onCrosshairMove(event) {
      const { hoveredMarkerId, point } = event;
      if (typeof hoveredMarkerId === 'number') {
        const yOffset = 5;
        const x = Math.round(point.x);
        const y = Math.round(point.y) + yOffset;

        const newStyle = {
          display: 'block',
          left: `${x}px`,
          top: `${y}px`,
          borderColor: '#26a69a',
        };
        if (hoveredMarkerId < 0) {
          // open
          const pos = summary.positions[-hoveredMarkerId - 1];
          setTooltipText(`cost: ${pos.cost.toFixed(8)}`);
        } else {
          // close
          const pos = summary.positions[hoveredMarkerId - 1];
          if (pos.roi < 0) {
            newStyle.borderColor = '#ef5350';
          }
          setTooltipText(
            '' +
              `gain: ${pos.gain.toFixed(8)}\n` +
              `profit: ${pos.profit.toFixed(8)}\n` +
              `duration: ${pos.duration}\n` +
              `roi: ${fmtPct(pos.roi)}\n` +
              `aroi: ${fmtPct(pos.annualizedRoi)}`,
          );
        }
        setTooltipStyle((style) => ({ ...style, ...newStyle }));
      } else if (tooltipRef.current.style.display !== 'none') {
        setTooltipStyle((style) => ({ ...style, display: 'none' }));
      }
    }
    chart.subscribeCrosshairMove(onCrosshairMove);

    // Line graph for running balance.
    chart
      .addLineSeries({
        priceScaleId: 'left',
        lineWidth: 1.2,
      })
      .setData(
        summary.positions.reduce(
          ([quote, points], pos) => {
            const newQuote = quote + pos.profit;
            points.push({
              time: timestamp(pos.closeTime),
              value: newQuote,
            });
            return [newQuote, points];
          },
          [
            summary.quote,
            [
              {
                time: timestamp(summary.start),
                value: summary.quote,
              },
            ],
          ],
        )[1],
      );

    // Fit everything into view.
    chart.timeScale().fitContent();

    return () => chart.unsubscribeCrosshairMove(onCrosshairMove);
  }, [symbol, candles, summary, palette]);

  return (
    <Box my={1} style={{ position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%' }} />
      <div ref={tooltipRef} style={tooltipStyle}>
        <Typography variant="caption">{tooltipText}</Typography>
      </div>
    </Box>
  );
}
