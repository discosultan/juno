// TODO: Fetch all of this from BE.
export const Strategies = [
  'fourweekrule',
  'triplema',
  'doublema',
  'doublemastoch',
  'singlema',
  'sig_fourweekrule',
  'sig_triplema',
  'sigosc_triplema_rsi',
  'sigosc_doublema_rsi',
];
export const StopLosses = [
  'noop',
  'basic',
  'basicplustrailing',
  'trailing',
  // 'legacy',
];
export const TakeProfits = [
  'noop',
  'basic',
  'trending',
  // 'legacy',
];
export const Symbols = [
  'ada-btc',
  'dash-btc',
  'eos-btc',
  'eth-btc',
  'link-btc',
  'ltc-btc',
  'xmr-btc',
  'xrp-btc',
];
export const Intervals = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
export const MissedCandlePolicies = ['ignore', 'restart', 'last'];
