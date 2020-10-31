trap 'kill %1' SIGINT
cargo run --release -p juno_warp_rs & npm --prefix juno_dashboard start
