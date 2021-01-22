mod backtest;
mod candles;
mod optimize;

pub use backtest::routes as backtest;
pub use candles::routes as candles;
pub use optimize::routes as optimize;

use std::fmt;
use warp::{reject, Rejection};

#[derive(Debug)]
pub(crate) struct CustomReject(anyhow::Error);

impl fmt::Display for CustomReject {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}

impl reject::Reject for CustomReject {}

pub(crate) fn custom_reject(error: impl Into<anyhow::Error>) -> Rejection {
    reject::custom(CustomReject(error.into()))
}
