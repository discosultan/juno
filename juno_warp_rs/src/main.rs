mod routes;

use warp::Filter;

#[tokio::main]
async fn main() {
    let hello = warp::path::end().map(|| "hello world");

    let routes = hello.or(routes::optimize());

    let port = 3030;

    println!("listening on port {}", port);
    warp::serve(routes).run(([127, 0, 0, 1], port)).await;
}
