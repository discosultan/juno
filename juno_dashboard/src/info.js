export const Strategies = [
  'fourweekrule',
  'triplema',
  'doublema',
  'singlema',
  'sig_fourweekrule',
  'sig_triplema',
  'sigosc_triplema_rsi',
  'sigosc_doublema_rsi',
  'sigosc_fourweekrule_rsi_prevent',
];
export const StopLosses = [
  'noop',
  'basic',
  'trailing',
  // 'legacy',
];
export const TakeProfits = [
  'noop',
  'basic',
  'trending',
  // 'legacy',
];
export const Symbols = ['eth-btc', 'ltc-btc', 'xrp-btc', 'xmr-btc', 'ada-btc', 'eos-btc'];
export const Intervals = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
export const MissedCandlePolicies = ['ignore', 'restart', 'last'];
