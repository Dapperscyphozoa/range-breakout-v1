"""
range-breakout-v1 — signal detector for trend-continuation breakouts.

Thesis: where range-fade fails (majors trending through "ranges"), the right
trade is the OPPOSITE — buy the breakout up, sell the breakdown. Trigger fires
when price is at a range extreme WITH momentum confirming the breakout direction
AND the higher-timeframe trend supports continuation.

Trigger:
  LONG  CONTINUATION:   pos_in_range >= 0.90 AND mom > +0.3% AND HTF_slope >  +threshold
  SHORT CONTINUATION:   pos_in_range <= 0.10 AND mom < -0.3% AND HTF_slope <  -threshold

Geometry:
  Entry: current close
  SL:    range midpoint   (breakout fails if price retraces to mid)
  TP:    current ± range_width (one full range extension)

Tunable via STRATEGY_* env vars:
  STRATEGY_LOOKBACK_BARS         default 24
  STRATEGY_POS_EXTREME_HIGH      default 0.90
  STRATEGY_POS_EXTREME_LOW       default 0.10
  STRATEGY_MOMENTUM_BARS         default 3
  STRATEGY_MOMENTUM_MIN_PCT      default 0.003   (0.3%)
  STRATEGY_MIN_RANGE_PCT         default 0.025
  STRATEGY_TP_RANGE_MULT         default 1.0
  STRATEGY_MIN_RR                default 1.0
  STRATEGY_ALLOW_REGIMES         default "range,chop,trend_up,trend_down"
  STRATEGY_HTF_SMA_PERIOD        default 200
  STRATEGY_HTF_SLOPE_LOOKBACK    default 30
  STRATEGY_HTF_SLOPE_THRESHOLD   default 0.005
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional

from .config import STRATEGY_PARAMS, TRADE_PARAMS
from .regime import classify_latest_bar


def calc_atr(highs, lows, closes, period: int = 14) -> float:
    h_s = pd.Series(highs); l_s = pd.Series(lows)
    pc = pd.Series(closes).shift(1)
    tr = pd.concat([h_s - l_s, (h_s - pc).abs(), (l_s - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _get(name, default):
    v = STRATEGY_PARAMS.get(name, default)
    try:
        return type(default)(v)
    except (TypeError, ValueError):
        return default


def _htf_slope(closes, sma_period, lag):
    if len(closes) < sma_period + lag + 1: return None
    s = pd.Series(closes).rolling(sma_period).mean()
    a = float(s.iloc[-1]); b = float(s.iloc[-lag])
    if pd.isna(a) or pd.isna(b) or b <= 0: return None
    return (a - b) / b


def evaluate_latest_bar(df: pd.DataFrame) -> Optional[dict]:
    lookback      = _get("lookback_bars", 24)
    pos_high      = _get("pos_extreme_high", 0.90)
    pos_low       = _get("pos_extreme_low", 0.10)
    momentum_bars = _get("momentum_bars", 3)
    mom_min       = _get("momentum_min_pct", 0.003)
    min_range_pct = _get("min_range_pct", 0.025)
    tp_mult       = _get("tp_range_mult", 1.0)
    min_rr        = _get("min_rr", 1.0)
    htf_sma       = _get("htf_sma_period", 200)
    htf_lag       = _get("htf_slope_lookback", 30)
    htf_thresh    = _get("htf_slope_threshold", 0.005)
    allow_str     = str(STRATEGY_PARAMS.get("allow_regimes", "range,chop,trend_up,trend_down"))
    allow_regimes = {s.strip() for s in allow_str.split(",") if s.strip()}

    min_history = max(htf_sma + htf_lag + 5, lookback + momentum_bars + 5)
    if df is None or len(df) < min_history: return None

    regime = classify_latest_bar(df)
    if regime is None or regime not in allow_regimes: return None

    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    last_close = float(closes[-1])

    last_atr = calc_atr(highs, lows, closes, TRADE_PARAMS.get("atr_period", 14))
    if not np.isfinite(last_atr) or last_atr <= 0: return None

    htf = _htf_slope(closes, htf_sma, htf_lag)
    if htf is None: return None
    allow_long  = htf > htf_thresh
    allow_short = htf < -htf_thresh

    range_high = float(highs[-lookback:].max())
    range_low  = float(lows[-lookback:].min())
    range_width = range_high - range_low
    if range_width <= 0 or range_low <= 0: return None
    range_pct = range_width / range_low
    if range_pct < min_range_pct: return None

    pos_in_range = (last_close - range_low) / range_width
    momentum_pct = (last_close - float(closes[-1 - momentum_bars])) / float(closes[-1 - momentum_bars])
    range_mid = (range_high + range_low) / 2

    # LONG continuation: at top of range, momentum up, trend up
    if pos_in_range >= pos_high and momentum_pct > mom_min and allow_long:
        sl_px = range_mid
        tp_px = last_close + range_width * tp_mult
        risk = last_close - sl_px; reward = tp_px - last_close
        if risk <= 0 or reward <= 0 or reward / risk < min_rr: return None
        return {
            "fire_ts":       df.index[-1],
            "ref_price":     last_close,
            "atr":           last_atr,
            "trade_side":    "B",
            "is_long":       True,
            "sl_px":         float(sl_px),
            "tp_px":         float(tp_px),
            "max_hold_bars": int(TRADE_PARAMS.get("max_hold_bars", 24)),
            "fire_reason":   "range_breakout_long",
            "range_high":    range_high,
            "range_low":     range_low,
            "range_pct":     range_pct,
            "pos_in_range":  pos_in_range,
            "momentum_pct":  momentum_pct,
            "htf_slope":     htf,
            "regime":        regime,
            "computed_rr":   reward / risk,
        }

    # SHORT continuation: at bottom, momentum down, trend down
    if pos_in_range <= pos_low and momentum_pct < -mom_min and allow_short:
        sl_px = range_mid
        tp_px = last_close - range_width * tp_mult
        risk = sl_px - last_close; reward = last_close - tp_px
        if risk <= 0 or reward <= 0 or reward / risk < min_rr: return None
        return {
            "fire_ts":       df.index[-1],
            "ref_price":     last_close,
            "atr":           last_atr,
            "trade_side":    "A",
            "is_long":       False,
            "sl_px":         float(sl_px),
            "tp_px":         float(tp_px),
            "max_hold_bars": int(TRADE_PARAMS.get("max_hold_bars", 24)),
            "fire_reason":   "range_breakout_short",
            "range_high":    range_high,
            "range_low":     range_low,
            "range_pct":     range_pct,
            "pos_in_range":  pos_in_range,
            "momentum_pct":  momentum_pct,
            "htf_slope":     htf,
            "regime":        regime,
            "computed_rr":   reward / risk,
        }

    return None
