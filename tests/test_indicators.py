from decimal import Decimal
from typing import TypedDict

import pytest

from juno import indicators
from juno.path import full_path, load_yaml_file


class IndicatorData(TypedDict):
    inputs: list[list[str]]
    outputs: list[list[str]]


IndicatorSources = dict[str, dict[str, IndicatorData]]


@pytest.fixture(scope="module")
def data() -> IndicatorSources:
    # Load inputs / expected outputs for all indicators.
    return {
        file[: file.index("_indicators.yaml")]: load_yaml_file(
            full_path(__file__, f"./data/{file}")
        )
        for file in [
            "quant_connect_indicators.yaml",
            "stock_charts_indicators.yaml",
            "stock_market_indicators.yaml",
            "trading_view_indicators.yaml",
            "tulip_indicators.yaml",
        ]
    }


def test_adx(data: IndicatorSources) -> None:
    _assert(indicators.Adx(14), data["tulip"]["adx"], 4)


def test_adxr(data: IndicatorSources) -> None:
    _assert(indicators.Adxr(14), data["tulip"]["adxr"], 4)


def test_alma(data: IndicatorSources) -> None:
    _assert(indicators.Alma(9, 6), data["quant_connect"]["alma"], 7)


def test_atr(data: IndicatorSources) -> None:
    _assert(indicators.Atr(4), data["tulip"]["atr"], 4)


def test_atr2_ema(data: IndicatorSources) -> None:
    _assert(indicators.Atr2(3, "ema"), data["trading_view"]["atr2_ema"], 2)


def test_atr2_rma(data: IndicatorSources) -> None:
    _assert(indicators.Atr2(3, "rma"), data["trading_view"]["atr2_rma"], 2)


def test_atr2_sma(data: IndicatorSources) -> None:
    _assert(indicators.Atr2(3, "sma"), data["trading_view"]["atr2_sma"], 2)


def test_atr2_wma(data: IndicatorSources) -> None:
    _assert(indicators.Atr2(3, "wma"), data["trading_view"]["atr2_wma"], 2)


def test_bbands(data: IndicatorSources) -> None:
    _assert(indicators.Bbands(5, Decimal("2.0")), data["tulip"]["bbands"], 4)


def test_cci(data: IndicatorSources) -> None:
    _assert(indicators.Cci(5), data["tulip"]["cci"], 4)


def test_chaikin_oscillator(data: IndicatorSources) -> None:
    _assert(indicators.ChaikinOscillator(3, 10), data["stock_market"]["chaikin_oscillator"], 8)


def test_chandelier_exit_1(data: IndicatorSources) -> None:
    _assert(
        indicators.ChandelierExit(2, 2, 2, 3, True), data["trading_view"]["chandelier_exit_1"], 2
    )


def test_chandelier_exit_2(data: IndicatorSources) -> None:
    _assert(
        indicators.ChandelierExit(2, 2, 2, 3, False), data["trading_view"]["chandelier_exit_2"], 2
    )


def test_chandelier_exit_3(data: IndicatorSources) -> None:
    _assert(
        indicators.ChandelierExit(2, 2, 2, 3, True),
        data["trading_view"]["chandelier_exit_3"],
        2,
    )


def test_darvas_box(data: IndicatorSources) -> None:
    _assert(indicators.DarvasBox(5), data["trading_view"]["darvas_box"], 2)


def test_dema(data: IndicatorSources) -> None:
    _assert(indicators.Dema(5), data["tulip"]["dema"], 4)


def test_di(data: IndicatorSources) -> None:
    _assert(indicators.DI(14), data["tulip"]["di"], 4)


def test_dm(data: IndicatorSources) -> None:
    _assert(indicators.DM(14), data["tulip"]["dm"], 4)


def test_dx(data: IndicatorSources) -> None:
    _assert(indicators.DX(14), data["tulip"]["dx"], 4)


def test_ema(data: IndicatorSources) -> None:
    _assert(indicators.Ema(5), data["tulip"]["ema"], 3)


def test_kama(data: IndicatorSources) -> None:
    # Precision should be 4 but is drifting off.
    _assert(indicators.Kama(4), data["tulip"]["kama"], 3)


def test_kvo(data: IndicatorSources) -> None:
    _assert(indicators.Kvo(34, 55), data["tulip"]["kvo"], 3)


def test_lsma(data: IndicatorSources) -> None:
    _assert(indicators.Lsma(5), data["trading_view"]["lsma"], 2)


def test_macd(data: IndicatorSources) -> None:
    _assert(indicators.Macd(12, 26, 9), data["tulip"]["macd"], 9)


def test_obv(data: IndicatorSources) -> None:
    _assert(indicators.Obv(), data["tulip"]["obv"], 4)


def test_obv2(data: IndicatorSources) -> None:
    _assert(indicators.Obv2(21), data["stock_market"]["obv2"], 8)


def test_rsi(data: IndicatorSources) -> None:
    _assert(indicators.Rsi(5), data["tulip"]["rsi"], 4)


def test_sma(data: IndicatorSources) -> None:
    _assert(indicators.Sma(5), data["tulip"]["sma"], 3)


def test_stoch(data: IndicatorSources) -> None:
    _assert(indicators.Stoch(5, 3, 3), data["tulip"]["stoch"], 4)


def test_stochrsi(data: IndicatorSources) -> None:
    _assert(indicators.StochRsi(5), data["tulip"]["stochrsi"], 4)


def test_tsi(data: IndicatorSources) -> None:
    # Precision should be 2 but it's drifting off.
    _assert(indicators.Tsi(25, 13), data["stock_charts"]["tsi"], 1)


def test_wma(data: IndicatorSources) -> None:
    _assert(indicators.Wma(3), data["trading_view"]["wma"], 2)


def test_zlsma(data: IndicatorSources) -> None:
    _assert(indicators.Zlsma(2), data["trading_view"]["zlsma"], 2)


def _assert(indicator, data: IndicatorData, precision: int) -> None:
    inputs = data["inputs"]
    expected_outputs = data["outputs"]
    input_len, output_len = len(inputs[0]), len(expected_outputs[0])
    offset = input_len - output_len
    for i in range(0, input_len):
        input_ = [Decimal(input_[i]) for input_ in inputs]
        outputs = indicator.update(*input_)
        if not isinstance(outputs, tuple):
            outputs = (outputs,)
        assert len(outputs) == len(expected_outputs)

        if i >= offset:
            assert indicator.mature
            for j in range(0, len(outputs)):
                expected_output = expected_outputs[j][i - offset]
                # "*" is a special symbol and allows any value.
                if expected_output != "*":
                    assert pytest.approx(outputs[j], abs=10**-precision) == Decimal(
                        expected_output
                    ), (
                        f"Failed at index {i} offset {offset} with inputs {input_} and outputs "
                        f"{outputs}"
                    )
        else:
            assert not indicator.mature
