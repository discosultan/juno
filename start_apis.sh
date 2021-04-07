trap 'kill %1' SIGINT
cargo run -p juno_warp_rs & python api.py
