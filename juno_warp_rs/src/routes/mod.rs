mod backtest;
mod candles;
mod optimize;

pub use backtest::route as backtest;
pub use candles::route as candles;
pub use optimize::route as optimize;

use std::fmt::Display;

#[derive(Debug)]
pub(crate) struct CustomReject(anyhow::Error);

impl Display for CustomReject {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(f)
    }
}

impl warp::reject::Reject for CustomReject {}

pub(crate) fn custom_reject(error: impl Into<anyhow::Error>) -> warp::Rejection {
    warp::reject::custom(CustomReject(error.into()))
}
