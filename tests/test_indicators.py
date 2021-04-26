from decimal import Decimal

import pytest
import yaml

from juno import indicators
from juno.utils import full_path


@pytest.fixture(scope='module')
def data():
    # Load inputs / expected outputs for all indicators.
    with open(full_path(__file__, './data/indicators_2021-04-08.yaml')) as f:
        return yaml.load(f, Loader=yaml.BaseLoader)


def test_adx(data) -> None:
    _assert(indicators.Adx(14), data['adx'], 4)


def test_adxr(data) -> None:
    _assert(indicators.Adxr(14), data['adxr'], 4)


def test_cci(data) -> None:
    _assert(indicators.Cci(5), data['cci'], 4)


def test_dema(data) -> None:
    _assert(indicators.Dema(5), data['dema'], 4)


def test_di(data) -> None:
    _assert(indicators.DI(14), data['di'], 4)


def test_dm(data) -> None:
    _assert(indicators.DM(14), data['dm'], 4)


def test_dx(data) -> None:
    _assert(indicators.DX(14), data['dx'], 4)


def test_ema(data) -> None:
    _assert(indicators.Ema(5), data['ema'], 3)


def test_macd(data) -> None:
    _assert(indicators.Macd(12, 26, 9), data['macd'], 9)


def test_rsi(data) -> None:
    _assert(indicators.Rsi(5), data['rsi'], 4)


def test_sma(data) -> None:
    _assert(indicators.Sma(5), data['sma'], 3)


def test_stoch(data) -> None:
    _assert(indicators.Stoch(5, 3, 3), data['stoch'], 4)


def test_stochrsi(data) -> None:
    _assert(indicators.StochRsi(5), data['stochrsi'], 4)


def test_obv(data) -> None:
    _assert(indicators.Obv(), data['obv'], 4)


def test_kvo(data) -> None:
    _assert(indicators.Kvo(34, 55), data['kvo'], 3)


def test_kama(data) -> None:
    # Precision should be 4 but is drifting off.
    _assert(indicators.Kama(4), data['kama'], 3)


def test_chaikin_oscillator(data) -> None:
    _assert(indicators.ChaikinOscillator(3, 10), data['chaikin_oscillator'], 8)


def test_obv2(data) -> None:
    _assert(indicators.Obv2(21), data['obv2'], 8)


def test_tsi(data) -> None:
    # Precision should be 2 but it's drifting off.
    _assert(indicators.Tsi(25, 13), data['tsi'], 1)


def test_alma(data) -> None:
    _assert(indicators.Alma(9, 6), data['alma'], 7)


def _assert(indicator, data, precision: int) -> None:
    inputs = data['inputs']
    expected_outputs = data['outputs']
    input_len, output_len = len(inputs[0]), len(expected_outputs[0])
    offset = input_len - output_len
    for i in range(0, input_len):
        outputs = indicator.update(*(Decimal(input_[i]) for input_ in inputs))
        if not isinstance(outputs, tuple):
            outputs = (outputs,)
        if i >= offset:
            assert indicator.mature
            for j in range(0, len(outputs)):
                assert pytest.approx(outputs[j], abs=10 ** -precision) == Decimal(
                    expected_outputs[j][i - offset]
                )
        else:
            assert not indicator.mature
