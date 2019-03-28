from decimal import Decimal

import pytest

from juno.indicators import (DI, DM, DX, Adx, Adxr, Cci, Dema, Ema, Macd, Rsi, Sma, Stoch,
                             StochRsi, Tsi)


def test_adx():
    inputs = [
        [  # High.
            94.1875, 94.5000, 93.5000, 92.7500, 92.8750, 90.7500, 89.8750, 89.1250, 90.4375,
            90.0000, 88.5000, 87.7500, 87.0625, 85.8125, 86.5625, 90.3750, 91.3750, 92.2500,
            93.3750, 92.0625, 92.8750, 93.9375, 95.2500, 97.1250, 97.1875, 94.8750, 94.3125,
            93.3125, 94.1250, 96.9375, 101.125, 108.750, 115.000, 117.125, 115.000, 116.625,
            118.000, 119.250, 119.250, 118.812, 118.375, 119.938, 117.750, 118.625, 117.125,
            116.375, 113.875, 112.250, 113.688, 114.250
        ],
        [  # Low.
            92.1250, 91.9375, 91.5000, 90.3125, 90.5000, 84.3750, 86.4375, 86.4375, 88.2500,
            87.0625, 86.9375, 85.8750, 85.0000, 84.5000, 84.3750, 88.4375, 88.3750, 89.5000,
            91.0000, 89.5000, 89.5625, 90.8750, 92.8750, 95.7344, 94.7500, 92.8750, 91.6875,
            91.4375, 92.2500, 92.7500, 95.3125, 98.5000, 108.938, 113.625, 111.188, 110.625,
            115.125, 116.750, 116.125, 117.062, 116.812, 117.125, 116.250, 112.000, 112.250,
            109.375, 108.375, 107.312, 111.375, 108.688
        ],
        [  # Close.
            92.3750, 92.5625, 92.0000, 91.7500, 91.5625, 89.9375, 88.8750, 87.1250, 89.6250,
            89.1875, 87.0000, 87.3125, 85.0000, 84.9375, 86.0000, 89.8125, 89.6250, 91.6875,
            91.1250, 90.1875, 91.0469, 93.1875, 94.8125, 96.1250, 95.4375, 93.0000, 91.7500,
            92.7500, 93.8750, 96.6250, 98.6875, 108.438, 113.688, 115.250, 112.750, 115.875,
            117.562, 117.438, 119.125, 117.500, 117.938, 117.625, 116.750, 116.562, 112.625,
            113.812, 110.000, 111.438, 112.250, 109.375
        ]
    ]
    # Value 29.5118 was corrected to 29.5117.
    outputs = [[
        18.4798, 17.7329, 16.6402, 16.4608, 17.5570, 19.9758, 22.9245, 25.8535, 27.6536, 29.5117,
        31.3907, 33.2726, 34.7625, 36.1460, 37.3151, 38.6246, 39.4151, 38.3660, 37.3919, 35.4565,
        33.3321, 31.0167, 29.3056, 27.5566
    ]]
    _assert(Adx(14), inputs, outputs, 4)


def test_adxr():
    inputs = [
        [  # High.
            94.1875, 94.5000, 93.5000, 92.7500, 92.8750, 90.7500, 89.8750, 89.1250, 90.4375,
            90.0000, 88.5000, 87.7500, 87.0625, 85.8125, 86.5625, 90.3750, 91.3750, 92.2500,
            93.3750, 92.0625, 92.8750, 93.9375, 95.2500, 97.1250, 97.1875, 94.8750, 94.3125,
            93.3125, 94.1250, 96.9375, 101.125, 108.750, 115.000, 117.125, 115.000, 116.625,
            118.000, 119.250, 119.250, 118.812, 118.375, 119.938, 117.750, 118.625, 117.125,
            116.375, 113.875, 112.250, 113.688, 114.250
        ],
        [  # Low.
            92.1250, 91.9375, 91.5000, 90.3125, 90.5000, 84.3750, 86.4375, 86.4375, 88.2500,
            87.0625, 86.9375, 85.8750, 85.0000, 84.5000, 84.3750, 88.4375, 88.3750, 89.5000,
            91.0000, 89.5000, 89.5625, 90.8750, 92.8750, 95.7344, 94.7500, 92.8750, 91.6875,
            91.4375, 92.2500, 92.7500, 95.3125, 98.5000, 108.938, 113.625, 111.188, 110.625,
            115.125, 116.750, 116.125, 117.062, 116.812, 117.125, 116.250, 112.000, 112.250,
            109.375, 108.375, 107.312, 111.375, 108.688
        ],
        [  # Close.
            92.3750, 92.5625, 92.0000, 91.7500, 91.5625, 89.9375, 88.8750, 87.1250, 89.6250,
            89.1875, 87.0000, 87.3125, 85.0000, 84.9375, 86.0000, 89.8125, 89.6250, 91.6875,
            91.1250, 90.1875, 91.0469, 93.1875, 94.8125, 96.1250, 95.4375, 93.0000, 91.7500,
            92.7500, 93.8750, 96.6250, 98.6875, 108.438, 113.688, 115.250, 112.750, 115.875,
            117.562, 117.438, 119.125, 117.500, 117.938, 117.625, 116.750, 116.562, 112.625,
            113.812, 110.000, 111.438, 112.250, 109.375
        ]
    ]
    outputs = [[
        27.3129, 27.5240, 27.6324, 27.9379, 27.9615, 28.6838, 29.1905, 29.5928, 29.3351, 29.4087,
        29.4736
    ]]
    _assert(Adxr(14), inputs, outputs, 4)


def test_cci():
    inputs = [
        [  # High.
            15.1250, 15.0520, 14.8173, 14.6900, 14.7967, 14.7940, 14.0930, 14.7000, 14.5255,
            14.6579, 14.7842, 14.8273
        ],
        [  # Low.
            14.9360, 14.6267, 14.5557, 14.4600, 14.5483, 13.9347, 13.8223, 14.0200, 14.2652,
            14.3773, 14.5527, 14.3309
        ],
        [  # Close.
            14.9360, 14.7520, 14.5857, 14.6000, 14.6983, 13.9460, 13.9827, 14.4500, 14.3452,
            14.4197, 14.5727, 14.4773
        ]
    ]
    outputs = [[18.0890, 84.4605, 109.1186, 46.6540]]
    _assert(Cci(5), inputs, outputs, 4)


def test_dema():
    inputs = [[
        122.906, 126.500, 140.406, 174.000, 159.812, 170.000, 176.750, 175.531, 166.562, 163.750,
        170.500, 175.000, 184.750, 202.781
    ]]
    outputs = [[172.0780, 168.5718, 170.2278, 173.4940, 180.5297, 194.1428]]
    _assert(Dema(5), inputs, outputs, 4)


def test_di():
    inputs = [
        [  # High.
            94.1875, 94.5000, 93.5000, 92.7500, 92.8750, 90.7500, 89.8750, 89.1250, 90.4375,
            90.0000, 88.5000, 87.7500, 87.0625, 85.8125, 86.5625, 90.3750, 91.3750, 92.2500,
            93.3750, 92.0625, 92.8750, 93.9375, 95.2500, 97.1250, 97.1875, 94.8750, 94.3125,
            93.3125, 94.1250, 96.9375, 101.125, 108.750, 115.000, 117.125, 115.000, 116.625,
            118.000, 119.250, 119.250, 118.812, 118.375, 119.938, 117.750, 118.625, 117.125,
            116.375, 113.875, 112.250, 113.688, 114.250
        ],
        [  # Low.
            92.1250, 91.9375, 91.5000, 90.3125, 90.5000, 84.3750, 86.4375, 86.4375, 88.2500,
            87.0625, 86.9375, 85.8750, 85.0000, 84.5000, 84.3750, 88.4375, 88.3750, 89.5000,
            91.0000, 89.5000, 89.5625, 90.8750, 92.8750, 95.7344, 94.7500, 92.8750, 91.6875,
            91.4375, 92.2500, 92.7500, 95.3125, 98.5000, 108.938, 113.625, 111.188, 110.625,
            115.125, 116.750, 116.125, 117.062, 116.812, 117.125, 116.250, 112.000, 112.250,
            109.375, 108.375, 107.312, 111.375, 108.688
        ],
        [  # Close.
            92.3750, 92.5625, 92.0000, 91.7500, 91.5625, 89.9375, 88.8750, 87.1250, 89.6250,
            89.1875, 87.0000, 87.3125, 85.0000, 84.9375, 86.0000, 89.8125, 89.6250, 91.6875,
            91.1250, 90.1875, 91.0469, 93.1875, 94.8125, 96.1250, 95.4375, 93.0000, 91.7500,
            92.7500, 93.8750, 96.6250, 98.6875, 108.438, 113.688, 115.250, 112.750, 115.875,
            117.562, 117.438, 119.125, 117.500, 117.938, 117.625, 116.750, 116.562, 112.625,
            113.812, 110.000, 111.438, 112.250, 109.375
        ]
    ]
    outputs = [
        [  # DI+.
            04.7619, 06.5404, 15.7975, 17.1685, 18.2181, 20.0392, 18.6830, 19.1863, 20.4108,
            22.5670, 26.1316, 24.4414, 22.7738, 21.1796, 20.0974, 21.3093, 26.4203, 32.9361,
            41.7807, 48.6368, 49.4654, 45.5589, 43.4969, 43.7326, 44.0367, 41.3368, 39.6102,
            38.3048, 39.3410, 38.0298, 32.8260, 29.6147, 25.7233, 23.1495, 21.1075, 22.8568,
            20.5857
        ],
        [  # DI-.
            31.2925, 29.4074, 26.0300, 23.9950, 22.2758, 20.8841, 23.4324, 21.4148, 19.7238,
            18.5036, 17.3764, 18.8646, 22.5699, 24.1567, 23.6037, 22.3726, 19.8789, 17.0398,
            13.4042, 11.6853, 10.8837, 14.7622, 13.1147, 12.4005, 11.7988, 12.3016, 11.7878,
            11.9265, 11.2104, 12.7810, 19.8102, 17.8722, 20.9206, 20.6465, 20.7242, 19.8413,
            22.6700
        ]
    ]
    _assert(DI(14), inputs, outputs, 4)


def test_dm():
    inputs = [
        [  # High.
            94.1875, 94.5000, 93.5000, 92.7500, 92.8750, 90.7500, 89.8750, 89.1250, 90.4375,
            90.0000, 88.5000, 87.7500, 87.0625, 85.8125, 86.5625, 90.3750, 91.3750, 92.2500,
            93.3750, 92.0625, 92.8750, 93.9375, 95.2500, 97.1250, 97.1875, 94.8750, 94.3125,
            93.3125, 94.1250, 96.9375, 101.125, 108.750, 115.000, 117.125, 115.000, 116.625,
            118.000, 119.250, 119.250, 118.812, 118.375, 119.938, 117.750, 118.625, 117.125,
            116.375, 113.875, 112.250, 113.688, 114.250
        ],
        [  # Low.
            92.1250, 91.9375, 91.5000, 90.3125, 90.5000, 84.3750, 86.4375, 86.4375, 88.2500,
            87.0625, 86.9375, 85.8750, 85.0000, 84.5000, 84.3750, 88.4375, 88.3750, 89.5000,
            91.0000, 89.5000, 89.5625, 90.8750, 92.8750, 95.7344, 94.7500, 92.8750, 91.6875,
            91.4375, 92.2500, 92.7500, 95.3125, 98.5000, 108.938, 113.625, 111.188, 110.625,
            115.125, 116.750, 116.125, 117.062, 116.812, 117.125, 116.250, 112.000, 112.250,
            109.375, 108.375, 107.312, 111.375, 108.688
        ]
    ]
    outputs = [
        [  # DM+.
            01.7500, 02.3750, 06.0179, 06.5880, 06.9924, 07.6180, 07.0738, 07.3811, 07.9163,
            08.6634, 09.9196, 09.2110, 08.5531, 07.9422, 07.3749, 07.6606, 09.9259, 13.4044,
            20.0720, 24.8882, 25.2355, 23.4330, 23.3842, 23.0889, 22.6897, 21.0690, 19.5641,
            18.1666, 18.4320, 17.1154, 15.8929, 14.7577, 13.7036, 12.7248, 11.8158, 12.4099,
            11.5234
        ],
        [  # DM-.
            11.5000, 10.6786, 09.9158, 09.2075, 08.5499, 07.9392, 08.8721, 08.2384, 07.6499,
            07.1035, 06.5961, 07.1093, 08.4765, 09.0586, 08.6615, 08.0428, 07.4684, 06.9349,
            06.4395, 05.9796, 05.5525, 07.5929, 07.0505, 06.5469, 06.0793, 06.2700, 05.8222,
            05.6563, 05.2523, 05.7521, 09.5913, 08.9062, 11.1450, 11.3489, 11.6013, 10.7726,
            12.6902
        ]
    ]
    _assert(DM(14), inputs, outputs, 4)


def test_dx():
    inputs = [
        [  # High.
            94.1875, 94.5000, 93.5000, 92.7500, 92.8750, 90.7500, 89.8750, 89.1250, 90.4375,
            90.0000, 88.5000, 87.7500, 87.0625, 85.8125, 86.5625, 90.3750, 91.3750, 92.2500,
            93.3750, 92.0625, 92.8750, 93.9375, 95.2500, 97.1250, 97.1875, 94.8750, 94.3125,
            93.3125, 94.1250, 96.9375, 101.125, 108.750, 115.000, 117.125, 115.000, 116.625,
            118.000, 119.250, 119.250, 118.812, 118.375, 119.938, 117.750, 118.625, 117.125,
            116.375, 113.875, 112.250, 113.688, 114.250
        ],
        [  # Low.
            92.1250, 91.9375, 91.5000, 90.3125, 90.5000, 84.3750, 86.4375, 86.4375, 88.2500,
            87.0625, 86.9375, 85.8750, 85.0000, 84.5000, 84.3750, 88.4375, 88.3750, 89.5000,
            91.0000, 89.5000, 89.5625, 90.8750, 92.8750, 95.7344, 94.7500, 92.8750, 91.6875,
            91.4375, 92.2500, 92.7500, 95.3125, 98.5000, 108.938, 113.625, 111.188, 110.625,
            115.125, 116.750, 116.125, 117.062, 116.812, 117.125, 116.250, 112.000, 112.250,
            109.375, 108.375, 107.312, 111.375, 108.688
        ],
        [  # Close.
            92.3750, 92.5625, 92.0000, 91.7500, 91.5625, 89.9375, 88.8750, 87.1250, 89.6250,
            89.1875, 87.0000, 87.3125, 85.0000, 84.9375, 86.0000, 89.8125, 89.6250, 91.6875,
            91.1250, 90.1875, 91.0469, 93.1875, 94.8125, 96.1250, 95.4375, 93.0000, 91.7500,
            92.7500, 93.8750, 96.6250, 98.6875, 108.438, 113.688, 115.250, 112.750, 115.875,
            117.562, 117.438, 119.125, 117.500, 117.938, 117.625, 116.750, 116.562, 112.625,
            113.812, 110.000, 111.438, 112.250, 109.375
        ]
    ]
    # Value 73.5850 was corrected to 73.5849.
    outputs = [[
        73.5849, 63.6115, 24.4637, 16.5840, 10.0206, 02.0645, 11.2771, 05.4886, 01.7117, 09.8936,
        20.1233, 12.8777, 00.4497, 06.5667, 08.0233, 02.4342, 14.1285, 31.8079, 51.4207, 61.2569,
        63.9309, 51.0546, 53.6679, 55.8176, 57.7373, 54.1312, 54.1312, 52.5138, 55.6475, 49.6919,
        24.7277, 24.7277, 10.2966, 05.7150, 00.9162, 07.0623, 04.8185
    ]]
    _assert(DX(14), inputs, outputs, 4)


def test_ema():
    inputs = [[25.000, 24.875, 24.781, 24.594, 24.500, 24.625, 25.219, 27.250]]
    outputs = [[25.000, 24.958, 24.899, 24.797, 24.698, 24.674, 24.856, 25.654]]
    _assert(Ema(5), inputs, outputs, 3)


def test_sma():
    inputs = [[25.000, 24.875, 24.781, 24.594, 24.500, 24.625, 25.219, 27.250]]
    outputs = [[24.750, 24.675, 24.744, 25.238]]
    _assert(Sma(5), inputs, outputs, 3)


def test_macd():
    inputs = [[
        63.750, 63.625, 63.000, 62.750, 63.250, 65.375, 66.000, 65.000, 64.875, 64.750, 64.375,
        64.375, 64.625, 64.375, 64.500, 65.250, 67.875, 68.000, 66.875, 66.250, 65.875, 66.000,
        65.875, 64.750, 63.000, 63.375, 63.375, 63.375, 63.875, 65.500, 63.250, 60.750, 57.250,
        59.125, 59.250, 58.500, 59.125, 59.750, 60.625, 60.500, 59.000, 59.500, 58.875, 59.625,
        59.875, 59.750, 59.625, 59.250, 58.875, 59.125, 60.875, 60.750, 61.125, 62.500, 63.250
    ]]
    outputs = [
        [  # MACD.
            +0.069246173, -0.056749361, -0.155174919, -0.193316296, -0.099255145, -0.192932945,
            -0.451916620, -0.912958472, -1.124556845, -1.268899802, -1.424364329, -1.483699214,
            -1.466784652, -1.371359250, -1.290278236, -1.324512659, -1.299028706, -1.311252875,
            -1.249862534, -1.168783424, -1.101261161, -1.045157593, -1.017413140, -1.012278166,
            -0.978102663, -0.808978519, -0.676278653, -0.536210248, -0.316924099, -0.084694969
        ],
        [  # Signal.
            +0.069246173, +0.044047066, +0.004202669, -0.035301124, -0.048091928, -0.077060132,
            -0.152031429, -0.304216838, -0.468284839, -0.628407832, -0.787599131, -0.926819148,
            -1.034812249, -1.102121649, -1.139752966, -1.176704905, -1.201169665, -1.223186307,
            -1.228521552, -1.216573927, -1.193511374, -1.163840617, -1.134555122, -1.110099731,
            -1.083700317, -1.028755957, -0.958260496, -0.873850447, -0.762465177, -0.626911135
        ],
        [  # Divergence.
            +0.000000000, -0.100796427, -0.159377588, -0.158015172, -0.051163217, -0.115872813,
            -0.299885190, -0.608741634, -0.656272006, -0.640491970, -0.636765198, -0.556880067,
            -0.431972403, -0.269237601, -0.150525270, -0.147807754, -0.097859041, -0.088066568,
            -0.021340981, +0.047790503, +0.092250213, +0.118683025, +0.117141982, +0.097821565,
            +0.105597654, +0.219777438, +0.281981844, +0.337640199, +0.445541078, +0.542216167
        ]
    ]
    _assert(Macd(12, 26, 9), inputs, outputs, 9)


def test_rsi():
    inputs = [[
        37.8750, 39.5000, 38.7500, 39.8125, 40.0000, 39.8750, 40.1875, 41.2500, 41.1250, 41.6250,
        41.2500, 40.1875, 39.9375, 39.9375, 40.5000, 41.9375, 42.2500, 42.2500, 41.8750, 41.8750
    ]]
    outputs = [[
        76.6667, 78.8679, 84.9158, 81.4863, 84.5968, 73.0851, 49.3173, 45.0119, 45.0119, 57.9252,
        75.9596, 78.4676, 78.4676, 65.6299, 65.6299
    ]]
    _assert(Rsi(5), inputs, outputs, 4)


def test_stoch():
    inputs = [
        [  # High.
            34.3750, 34.7500, 34.2188, 33.8281, 33.4375, 33.4688, 34.3750, 34.7188, 34.6250,
            34.9219, 34.9531, 35.0625, 34.7812, 34.3438, 34.5938, 34.3125, 34.2500, 34.1875,
            33.7812, 33.8125, 33.9688, 33.8750, 34.0156, 33.5312
        ],
        [  # Low.
            33.5312, 33.9062, 33.6875, 33.2500, 33.0000, 32.9375, 33.2500, 34.0469, 33.9375,
            34.0625, 34.4375, 34.5938, 33.7656, 33.2188, 33.9062, 32.6562, 32.7500, 33.1562,
            32.8594, 33.0000, 33.2969, 33.2812, 33.0312, 33.0156
        ],
        [  # Close.
            34.3125, 34.1250, 33.7500, 33.6406, 33.0156, 33.0469, 34.2969, 34.1406, 34.5469,
            34.3281, 34.8281, 34.8750, 33.7812, 34.2031, 34.4844, 32.6719, 34.0938, 33.2969,
            33.0625, 33.7969, 33.3281, 33.8750, 33.1094, 33.1875
        ]
    ]
    outputs = [
        [  # K.
            84.1524, 75.9890, 84.3623, 82.0235, 59.0655, 45.9745, 41.0782, 40.8947, 45.6496,
            33.7903, 40.5626, 40.9688, 42.7932, 61.2935, 45.5442, 38.8516
        ],
        [  # D.
            58.0105, 72.0631, 81.5012, 80.7916, 75.1504, 62.3545, 48.7061, 42.6491, 42.5409,
            40.1115, 40.0008, 38.4405, 41.4415, 48.3518, 49.8770, 48.5631
        ]
    ]
    _assert(Stoch(5, 3, 3), inputs, outputs, 4)


def test_stochrsi():
    inputs = [[
        37.8750, 39.5000, 38.7500, 39.8125, 40.0000, 39.8750, 40.1875, 41.2500, 41.1250, 41.6250,
        41.2500, 40.1875, 39.9375, 39.9375, 40.5000, 41.9375, 42.2500, 42.2500, 41.8750, 41.8750
    ]]
    outputs = [[
        0.9613, 0.0000, 0.0000, 0.0000, 0.0000, 0.4600, 1.0000, 1.0000, 1.0000, 0.3751, 0.0000
    ]]
    _assert(StochRsi(5), inputs, outputs, 4)


# Data taken from:
# https://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:true_strength_index
def test_tsi():
    inputs = [[
        1080.29, 1090.10, 1104.51, 1091.84, 1098.87, 1104.18, 1109.55, 1121.90, 1121.10, 1125.07,
        1124.66, 1125.59, 1142.71, 1139.78, 1134.28, 1124.83, 1148.67, 1142.16, 1147.70, 1144.73,
        1141.20, 1146.24, 1137.03, 1160.75, 1159.97, 1158.06, 1165.15, 1165.32, 1169.77, 1178.10,
        1173.81, 1176.19, 1184.71, 1165.90, 1178.17, 1180.26, 1183.08, 1185.62, 1185.64, 1182.45,
        1183.78, 1183.26, 1184.38, 1193.57, 1197.96, 1221.06, 1225.85, 1223.25, 1213.40, 1218.71,
        1213.54, 1199.21, 1197.75, 1178.34, 1178.59, 1196.69, 1199.73, 1197.84, 1180.73, 1198.35,
        1189.40, 1187.76, 1180.55, 1206.07, 1221.53, 1224.71, 1223.12, 1223.75, 1228.28, 1233.00,
        1240.40, 1240.46, 1241.59, 1235.23, 1242.87, 1243.91, 1247.08, 1254.60, 1258.84, 1256.77,
        1257.54, 1258.51, 1259.78, 1257.88, 1257.64, 1271.89, 1270.20, 1276.56, 1273.85, 1271.50,
        1269.75, 1274.48, 1285.96, 1283.76, 1293.24, 1295.02, 1281.92, 1280.26, 1283.35, 1290.84,
        1291.18, 1296.63, 1299.54, 1276.34, 1286.12, 1307.59, 1304.03, 1307.10, 1310.87, 1319.05,
        1324.57, 1320.88, 1321.87, 1329.15, 1332.32, 1328.01, 1336.32, 1340.43, 1343.01, 1315.44,
        1307.40, 1306.10, 1319.88, 1327.22, 1306.33, 1308.44, 1330.97, 1321.15, 1310.13, 1321.82,
        1320.02, 1295.11, 1304.28, 1296.39, 1281.87, 1256.88, 1273.72, 1279.20, 1298.38, 1293.77,
        1297.54, 1309.66, 1313.80, 1310.19, 1319.44, 1328.26, 1325.83, 1332.41, 1332.87, 1332.63,
        1335.54, 1333.51, 1328.17, 1324.46, 1314.16, 1314.41, 1314.52, 1319.68, 1305.14, 1312.62,
        1330.36, 1337.38, 1335.25, 1347.24, 1355.66, 1360.48, 1363.61, 1361.22, 1356.62, 1347.32,
        1335.10, 1340.20, 1346.29, 1357.16, 1342.08, 1348.65, 1337.77, 1329.47, 1328.98, 1340.68,
        1343.60, 1333.27, 1317.37, 1316.28, 1320.47, 1325.69, 1331.10, 1345.20, 1314.55, 1312.94,
        1300.16, 1286.17, 1284.94, 1279.56, 1289.00, 1270.98, 1271.83, 1287.87, 1265.42, 1267.64,
        1271.50, 1278.36, 1295.52, 1287.14, 1283.50, 1268.45, 1280.10, 1296.67, 1307.41, 1320.64,
        1339.67, 1337.88, 1339.22, 1353.22, 1343.80, 1319.49, 1313.64, 1317.72, 1308.87, 1316.14,
        1305.44, 1326.73, 1325.84, 1343.80, 1345.02, 1337.43, 1331.94, 1304.89, 1300.67, 1292.28,
        1286.94, 1254.05, 1260.34, 1200.07, 1199.38, 1119.46, 1172.53, 1120.76, 1172.64, 1178.81,
        1204.49, 1192.76, 1193.88, 1140.65, 1123.53, 1123.82, 1162.35, 1177.60, 1159.27, 1176.80,
        1210.08, 1212.92, 1218.89, 1204.42, 1173.97, 1165.24, 1198.62, 1185.90, 1154.23, 1162.27,
        1172.87, 1188.68, 1209.11, 1216.01, 1204.09, 1202.09, 1166.76, 1129.56, 1136.43, 1162.95,
        1175.38, 1151.06, 1160.40, 1131.42, 1099.23, 1123.95, 1144.04, 1164.97, 1155.46, 1194.89,
        1195.54, 1207.25, 1203.66, 1224.58, 1200.86, 1225.38, 1209.88, 1215.39, 1238.25, 1254.19,
        1229.05, 1242.00, 1284.59, 1285.08, 1253.30, 1218.28, 1237.90, 1261.15, 1253.23, 1261.12,
        1275.92, 1229.10, 1239.70, 1263.85, 1251.78, 1257.81, 1236.91, 1216.13, 1215.65, 1192.98,
        1188.04, 1161.79, 1158.67, 1192.55, 1195.19, 1246.96, 1244.58, 1244.28, 1257.08, 1258.47,
        1261.01, 1234.35, 1255.19, 1236.47, 1225.73, 1211.82, 1215.75, 1219.66, 1205.35, 1241.30,
        1243.72, 1254.00, 1265.33, 1265.43, 1249.64, 1263.02, 1257.60, 1277.06, 1277.30, 1281.06,
        1277.81, 1280.70, 1292.08, 1292.48, 1295.50, 1289.09, 1293.67, 1308.04, 1314.50, 1315.38,
        1316.00, 1314.65, 1326.06, 1318.43, 1316.33, 1313.01, 1312.41, 1324.09, 1325.54, 1344.90,
        1344.33, 1347.05, 1349.96, 1351.95, 1342.64, 1351.77, 1350.50, 1343.23, 1358.04, 1361.23,
        1362.21, 1357.66, 1363.46, 1365.74, 1367.59, 1372.18, 1365.68, 1374.09, 1369.63, 1364.33,
        1343.36, 1352.63, 1365.91, 1370.87, 1371.09, 1395.95, 1394.28, 1402.60, 1404.17, 1409.75,
        1405.52, 1402.89, 1392.78, 1397.11, 1416.51, 1412.52, 1405.54, 1403.28, 1408.47, 1419.04,
        1413.38, 1398.96, 1398.08, 1382.20, 1358.59, 1368.71, 1387.57, 1370.26, 1369.57, 1390.78,
        1385.14, 1376.92, 1378.53, 1366.94, 1371.97, 1390.69, 1399.98, 1403.36, 1397.91, 1405.82,
        1402.31, 1391.57, 1369.10, 1369.58, 1363.72, 1354.58, 1357.99, 1353.39, 1338.35, 1330.66,
        1324.80, 1304.86, 1295.22, 1315.99, 1316.63, 1318.86, 1320.68, 1317.82, 1332.42, 1313.32,
        1310.33, 1278.04, 1278.18, 1285.50, 1315.13, 1314.99, 1325.66, 1308.93, 1324.18, 1314.88,
        1329.10, 1342.84, 1344.78, 1357.98, 1355.69, 1325.51, 1335.02, 1313.72, 1319.99, 1331.85,
        1329.04, 1362.16, 1365.51, 1374.02, 1367.58, 1354.68, 1352.46, 1341.47, 1341.45, 1334.76,
        1356.78, 1353.64, 1363.67, 1372.78, 1376.51, 1362.66, 1350.52, 1338.31, 1337.89, 1360.02,
        1385.97, 1385.30, 1379.32, 1375.32, 1365.00, 1390.99, 1394.23, 1401.35, 1402.22, 1402.80,
        1405.87, 1404.11, 1403.93, 1405.53, 1415.51, 1418.16, 1418.13, 1413.17, 1413.49, 1402.08,
        1411.13, 1410.44, 1409.30, 1410.49
    ]]
    outputs = [[
        +11.74, +09.68, +07.85, +05.30, +06.77, +09.82, +12.49, +14.30, +15.80, +17.51, +19.42,
        +21.78, +23.71, +25.43, +25.69, +26.75, +27.73, +28.92, +30.75, +32.73, +33.92, +34.99,
        +36.01, +37.02, +37.39, +37.64, +39.65, +40.81, +42.55, +43.15, +42.91, +42.15, +42.15,
        +43.65, +44.13, +45.71, +47.18, +44.00, +41.01, +39.07, +38.55, +38.19, +38.65, +39.42,
        +32.99, +29.63, +30.19, +29.72, +29.76, +30.28, +31.68, +33.43, +33.93, +34.43, +35.68,
        +37.04, +37.07, +38.04, +39.27, +40.56, +34.67, +28.39, +23.32, +21.21, +20.55, +16.07,
        +13.00, +13.64, +12.49, +09.91, +09.42, +08.78, +04.78, +02.90, +00.48, -03.14, -08.67,
        -10.68, -11.51, -09.84, -09.01, -07.93, -05.72, -03.52, -02.13, +00.00, +02.66, +04.54,
        +06.77, +08.66, +10.20, +11.82, +12.90, +13.04, +12.59, +10.63, +09.02, +07.68, +07.26,
        +04.52, +03.39, +05.15, +07.54, +09.08, +11.97, +15.36, +18.65, +21.65, +23.62, +24.33,
        +23.06, +19.69, +17.67, +16.86, +17.64, +15.50, +14.71, +12.21, +08.90, +06.24, +05.77,
        +05.81, +04.22, +00.58, -02.41, -04.16, -04.75, -04.40, -01.95, -04.35, -06.36, -09.51,
        -13.58, -16.83, -19.95, -20.92, -23.50, -25.37, -24.29, -25.56, -26.18, -26.08, -24.95,
        -21.48, -19.57, -18.42, -18.97, -17.76, -14.56, -10.68, -06.04, -00.25, +04.00, +07.49,
        +11.68, +13.83, +12.51, +10.78, +09.81, +08.00, +07.28, +05.46, +06.19, +06.67, +08.83,
        +10.66, +11.22, +11.00, +07.58, +04.41, +00.97, -02.36, -08.38, -12.28, -20.39, -26.29,
        -35.58, -35.96, -38.59, -35.60, -33.07, -29.30, -27.03, -25.24, -26.03, -27.29, -28.23,
        -26.43, -24.05, -22.90, -20.90, -17.31, -14.31, -11.55, -09.98, -10.14, -10.67, -09.16,
        -08.57, -09.62, -10.00, -09.67, -08.47, -06.28, -04.11, -02.98, -02.16, -03.51, -06.66,
        -08.72, -08.69, -07.87, -08.53, -08.46, -09.95, -12.80, -13.41, -12.59, -10.62, -09.56,
        -06.33, -03.76, -01.03, +00.96, +03.77, +04.61, +06.62, +07.27, +08.09, +09.98, +12.34,
        +12.55, +13.39, +16.22, +18.46, +18.03, +15.30, +14.15, +14.39, +14.06, +14.18, +15.00,
        +12.62, +11.28, +11.42, +10.79, +10.58, +09.11, +06.64, +04.63, +01.62, -01.11, -04.87,
        -08.09, -08.46, -08.59, -05.29, -02.84, -00.90, +01.48, +03.50, +05.34, +05.01, +06.05,
        +05.56, +04.41, +02.49, +01.20, +00.42, -01.25, +00.00, +01.18, +02.87, +05.05, +06.84,
        +07.01, +08.12, +08.55, +10.33, +11.78, +13.26, +14.18, +15.16, +16.86, +18.31, +19.77,
        +20.25, +21.03, +22.88, +24.95, +26.75, +28.31, +29.44, +31.38, +31.74, +31.68, +31.05,
        +30.41, +31.01, +31.67, +34.13, +36.01, +37.80, +39.56, +41.21, +40.46, +40.73, +40.66,
        +38.88, +38.98, +39.38, +39.80, +39.05, +39.06, +39.31, +39.72, +40.56, +39.55, +39.68,
        +38.62, +36.36, +29.29, +25.13, +23.77, +23.40, +23.14, +26.10, +27.98, +30.36, +32.37,
        +34.55, +35.38, +35.47, +33.35, +32.12, +33.25, +33.28, +31.86, +30.26, +29.56, +30.18,
        +29.51, +26.07, +23.21, +17.96, +09.86, +05.18, +04.20, +01.09, -01.30, -00.40, -00.41,
        -01.41, -01.99, -03.80, -04.60, -02.91, -00.48, +01.83, +03.01, +04.86, +05.91, +05.39,
        +02.14, -00.35, -03.04, -06.26, -08.40, -10.66, -14.15, -17.76, -21.25, -25.96, -30.52,
        -30.73, -30.80, -30.50, -29.97, -29.79, -27.27, -27.00, -27.06, -29.96, -32.14, -32.69,
        -28.57, -25.45, -21.52, -19.95, -16.75, -15.13, -12.15, -08.25, -05.00, -01.01, +01.91,
        +01.04, +01.32, -00.60, -01.46, -00.95, -00.83, +02.46, +05.30, +08.29, +09.98, +09.99,
        +09.75, +08.40, +07.31, +05.69, +06.46, +06.75, +07.93, +09.76, +11.59, +11.44, +09.88,
        +07.21, +05.02, +05.53, +08.50, +10.72, +11.78, +12.15, +11.22, +12.91, +14.52, +16.44,
        +18.06, +19.43, +20.84, +21.77, +22.53, +23.33, +24.97, +26.61, +28.00, +28.29, +28.57,
        +26.60, +25.99, +25.35, +24.59, +24.09
    ]]
    _assert(Tsi(25, 13), inputs, outputs, 1)  # Precision should be 2 but it's drifting off.


def _assert(indicator, inputs, outputs, precision):
    input_len, output_len = len(inputs[0]), len(outputs[0])
    offset = input_len - output_len
    for i in range(0, input_len):
        indicator.update(*(Decimal(input[i]) for input in inputs))
        # Assert public values of an indicator.
        values = [v for k, v in vars(indicator).items() if not k.startswith('_')]
        if i >= offset:
            for j in range(0, len(values)):
                assert pytest.approx(
                    float(values[j]), abs=10**-precision) == outputs[j][i - offset]
