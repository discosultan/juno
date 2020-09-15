use juno_rs::{prelude::*, storages::list_candles};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let candles = list_candles(
        "binance",
        "eth-btc",
        DAY_MS,
        "2020-01-01".to_timestamp(),
        "2020-02-01".to_timestamp(),
    )?;
    println!("Hello, world!\n{:?}", candles);
    Ok(())
}
