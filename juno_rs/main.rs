use crate::{
    prelude::*,
    storages::list_candles,
};

fn main() {
    let candles = list_candles(
        "binance",
        "eth-btc",
        DAY_MS,
        "2020-01-01".to_interval(),
        "2020-02-01".to_interval(),
    );
    println!("Hello, world! {:?}", candles);
}
