use indicators::EmaParams;
use juno_rs::{
    indicators::{self, MAParams},
    statistics::CoreStatistics,
    stop_loss::{self, StopLossParams},
    storages,
    strategies::{FourWeekRuleParams, StrategyParams},
    take_profit::{self, TakeProfitParams},
    time::{TimestampStrExt, DAY_MS},
    trading::{trade, MissedCandlePolicy},
    Candle, ExchangeInfo,
};
use once_cell::sync::Lazy;
use std::{collections::HashMap, fs::File};

static EXPECTED_STATS: Lazy<HashMap<String, CoreStatistics>> = Lazy::new(|| {
    // Relative to juno_rs dir.
    let file =
        File::open("../tests/data/strategies.json").expect("unable to open strategies data file");
    serde_json::from_reader(file).expect("unable to deserialize strategy data")
});

static EXCHANGE_INFO: Lazy<ExchangeInfo> =
    Lazy::new(|| storages::get_exchange_info("binance").expect("unable to get exchange info"));

static CANDLES: Lazy<Vec<Candle>> = Lazy::new(|| {
    storages::list_candles(
        "binance",
        "eth-btc",
        DAY_MS,
        "2018-01-01".to_timestamp(),
        "2021-01-01".to_timestamp(),
    )
    .expect("unable to list candles")
});

#[test]
fn test_four_week_rule() {
    test_strategy(
        StrategyParams::FourWeekRule(FourWeekRuleParams {
            period: 28,
            ma: MAParams::Ema(EmaParams {
                period: 14,
                smoothing: None,
            }),
        }),
        "FourWeekRuleParams",
    )
}

fn test_strategy(strategy_params: StrategyParams, name: &str) {
    let summary = trade(
        &strategy_params,
        &StopLossParams::Noop(stop_loss::NoopParams {}),
        &TakeProfitParams::Noop(take_profit::NoopParams {}),
        &CANDLES,
        &EXCHANGE_INFO.fees["eth-btc"],
        &EXCHANGE_INFO.filters["eth-btc"],
        &EXCHANGE_INFO.borrow_info["eth-btc"]["eth"],
        2,
        DAY_MS,
        1.0,
        MissedCandlePolicy::Ignore,
        true,
        false,
    );
    let output = CoreStatistics::compose(&summary);
    assert_eq!(&output, &EXPECTED_STATS[name]);
}
