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
    let exchange_info = storages::get_exchange_info("binance")?;
    println!("{:?}", exchange_info.fees["eth-btc"]);
    println!("{:?}", exchange_info.filters["eth-btc"]);
    println!("{:?}", exchange_info.borrow_info["eth-btc"]);
    Ok(())
}
