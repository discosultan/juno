use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

mod agents;
mod filters;
mod indicators;
mod strategies;
mod utils;

use agents::{backtest, BacktestResult};
use filters::Filters;
use strategies::EmaEmaCx;

#[pyfunction]
pub fn emaemacx(
    candles: Vec<&Candle>,
    fees: &Fees,
    filters: &Filters,
    quote: f64,
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
) -> PyResult<BacktestResult> {
    let mut strategy = EmaEmaCx::new(
        short_period, long_period, neg_threshold, pos_threshold, persistence);
    Ok(backtest(strategy/*, candles, fees, filters*/, quote))
}

// This function name will become the name of the Python module!
#[pymodule]
fn juno_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_wrapped(wrap_pyfunction!(emaemacx))?;
    Ok(())
}

#[pyclass]
pub struct Candle {
    time: u64,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    closed: bool,
}

#[derive(Clone, Copy, PartialEq)]
pub enum Advice {
    None,
    Buy,
    Sell,
}

#[derive(Clone, Copy, PartialEq)]
pub enum Trend {
    Unknown,
    Up,
    Down,
}

#[pyclass]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

impl Fees {
    pub fn none() -> Self {
        Fees {
            maker: 0.0,
            taker: 0.0,
        }
    }
}
