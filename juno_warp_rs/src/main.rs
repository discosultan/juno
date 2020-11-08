mod routes;

use crate::routes::CustomReject;
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
        .or(routes::optimize())
        .or(routes::candles())
        .recover(handle_rejection);

    let port = 3030;

    println!("listening on port {}", port);
    warp::serve(routes).run(([127, 0, 0, 1], port)).await;
}

async fn handle_rejection(err: Rejection) -> Result<impl Reply, Infallible> {
    let message = err.find::<CustomReject>().unwrap();

    let json = warp::reply::json(&ErrorResponse {
        message: message.to_string(),
    });

    Ok(warp::reply::with_status(
        json,
        StatusCode::INTERNAL_SERVER_ERROR,
    ))
}
