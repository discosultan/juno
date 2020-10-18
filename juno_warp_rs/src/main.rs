use serde::Deserialize;
use warp::Filter;

#[derive(Debug, Deserialize)]
struct OptimizeParams {
    exchange: String,
    interval: String,
    start: String,
    end: String,
    quote: f64,
    training_symbols: Vec<String>,
    validation_symbols: Vec<String>,
}

#[tokio::main]
async fn main() {
    // GET /hello/warp => 200 OK with body "Hello, warp!"
    let hello = warp::path!("hello" / String)
        .map(|name| format!("Hello, {}!", name));

    let optimize = warp::path!("optimize")
        .and(warp::body::json())
        .map(|params: OptimizeParams| {
            println!("{:?}", params);
            "hello"
        });

    let routes = hello.or(optimize);
    let port = 3030;

    println!("listening on port {}", port);
    warp::serve(routes)
        .run(([127, 0, 0, 1], port))
        .await;
}
