use juno_rs::{
    chandler,
    indicators::{self, MAParams},
    statistics::CoreStatistics,
    stop_loss::{self, StopLossParams},
    storages,
    strategies::{self, StrategyParams},
    take_profit::{self, TakeProfitParams},
    time::{TimestampStrExt, DAY_MS},
    trading::{trade, MissedCandlePolicy, TraderParams, TradingParams, TradingSummary},
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
    chandler::list_candles(
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
        StrategyParams::FourWeekRule(strategies::FourWeekRuleParams {
            period: 28,
            ma: MAParams::Ema(indicators::EmaParams {
                period: 14,
                smoothing: None,
            }),
        }),
        "FourWeekRuleParams",
    );
}

#[test]
fn test_single_ma() {
    test_strategy(
        StrategyParams::SingleMA(strategies::SingleMAParams {
            ma: MAParams::Ema(indicators::EmaParams {
                period: 50,
                smoothing: None,
            }),
        }),
        "SingleMAParams",
    );
}

#[test]
fn test_double_ma() {
    test_strategy(
        StrategyParams::DoubleMA(strategies::DoubleMAParams {
            mas: (
                MAParams::Ema(indicators::EmaParams {
                    period: 5,
                    smoothing: None,
                }),
                MAParams::Ema(indicators::EmaParams {
                    period: 20,
                    smoothing: None,
                }),
            ),
        }),
        "DoubleMAParams",
    );
}

#[test]
fn test_triple_ma() {
    test_strategy(
        StrategyParams::TripleMA(strategies::TripleMAParams {
            mas: (
                MAParams::Ema(indicators::EmaParams {
                    period: 4,
                    smoothing: None,
                }),
                MAParams::Ema(indicators::EmaParams {
                    period: 9,
                    smoothing: None,
                }),
                MAParams::Ema(indicators::EmaParams {
                    period: 18,
                    smoothing: None,
                }),
            ),
        }),
        "TripleMAParams",
    );
}

fn test_strategy(strategy: StrategyParams, name: &str) {
    let summary = trade(
        &TradingParams {
            strategy,
            stop_loss: StopLossParams::Basic(stop_loss::BasicParams {
                up_threshold: 0.1,
                down_threshold: 0.1,
            }),
            take_profit: TakeProfitParams::Basic(take_profit::BasicParams {
                up_threshold: 0.1,
                down_threshold: 0.1,
            }),
            // stop_loss: StopLossParams::Noop(stop_loss::NoopParams {}),
            // take_profit: TakeProfitParams::Noop(take_profit::NoopParams {}),
            trader: TraderParams {
                interval: DAY_MS,
                missed_candle_policy: MissedCandlePolicy::Ignore,
            },
        },
        &CANDLES,
        &EXCHANGE_INFO.fees["eth-btc"],
        &EXCHANGE_INFO.filters["eth-btc"],
        &EXCHANGE_INFO.borrow_info["eth-btc"]["eth"],
        2,
        1.0,
        true,
        true,
    );
    // dump_summary(&summary);
    let output = CoreStatistics::compose(&summary);
    assert_stats(&output, &EXPECTED_STATS[name]);
}

fn assert_approx(left: f64, right: f64) {
    const EPSILON: f64 = 0.000001;
    if f64::abs(left - right) >= EPSILON {
        panic!(
            r#"assertion failed: `(left == right)`
  left: `{:?}`,
 right: `{:?}`"#,
            left, right
        )
    }
}

fn assert_stats(left: &CoreStatistics, right: &CoreStatistics) {
    assert_eq!(left.start, right.start);
    assert_eq!(left.end, right.end);
    assert_eq!(left.duration, right.duration);
    assert_approx(left.cost, right.cost);
    assert_approx(left.gain, right.gain);
    assert_approx(left.profit, right.profit);
    assert_approx(left.roi, right.roi);
    assert_approx(left.annualized_roi, right.annualized_roi);
    assert_approx(left.mean_position_profit, right.mean_position_profit);
    assert_eq!(left.mean_position_duration, right.mean_position_duration);
    assert_approx(left.max_drawdown, right.max_drawdown);
    assert_approx(left.mean_drawdown, right.mean_drawdown);
    assert_approx(
        left.return_over_max_drawdown,
        right.return_over_max_drawdown,
    );
    assert_eq!(left.num_positions, right.num_positions);
    assert_eq!(left.num_positions_in_profit, right.num_positions_in_profit);
    assert_eq!(left.num_positions_in_loss, right.num_positions_in_loss);
    assert_eq!(left.num_stop_losses, right.num_stop_losses);
    assert_eq!(left.num_take_profits, right.num_take_profits);
}

#[allow(dead_code)]
fn dump_summary(summary: &TradingSummary) {
    let file = File::create("../rs_dump.json").unwrap();
    serde_json::to_writer_pretty(file, summary).unwrap();
}
