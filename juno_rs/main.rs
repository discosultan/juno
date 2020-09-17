use juno_rs::{prelude::*, storages};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let candles = storages::list_candles(
        "binance",
        "eth-btc",
        DAY_MS,
        "2020-01-01".to_timestamp(),
        "2020-02-01".to_timestamp(),
    )?;
    println!("{:?}", candles);
    Ok(())
}
