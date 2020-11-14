mod routes;

use serde::Serialize;
use std::{convert::Infallible, result::Result};
use warp::{http::StatusCode, Filter, Rejection, Reply};

#[derive(Serialize)]
struct ErrorResponse {
    message: String,
}

#[tokio::main]
async fn main() {
    let hello = warp::path::end().map(|| "hello world");

    let routes = hello
        .or(routes::backtest())
        .or(routes::optimize())
        .or(routes::candles())
        .recover(handle_rejection);

    let port = 3030;

    println!("listening on port {}", port);
    warp::serve(routes).run(([127, 0, 0, 1], port)).await;
}

async fn handle_rejection(err: Rejection) -> Result<impl Reply, Infallible> {
    let (status, message) = if err.is_not_found() {
        (StatusCode::NOT_FOUND, "Not found".to_owned())
    } else {
        (StatusCode::INTERNAL_SERVER_ERROR, format!("{:?}", err))
    };

    let json = warp::reply::json(&ErrorResponse { message: message });

    Ok(warp::reply::with_status(json, status))
}
