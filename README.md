# range-breakout-v1

Trend-continuation engine. Trades the failures of range-fade.

## Thesis
On trending coins (majors), what looks like a "range" locally is actually a consolidation
inside a larger trend. The bounce / rejection at range edges doesn't hold — price breaks
through. Trade the break, not the bounce.

## Entry
- LONG  CONTINUATION:  price in top 10% of 24-bar range, +momentum, 200-SMA sloping up
- SHORT CONTINUATION:  price in bottom 10% of range, -momentum, 200-SMA sloping down

## Geometry
- Entry: current close
- SL: range midpoint (breakout failed if price retraces to mid)
- TP: ±1 full range width extension
- HTF filter: only fires with-trend (no counter-trend breakouts)

## Universe
Tuned for majors that fail range-fade: BTC, ETH, SOL, LINK, BNB
(AAVE excluded — neither strategy has edge on it)

## Backtest (90d, in-sample)
~53 trades, WR ~40%, PF ~1.7+, +0.4R/trade

## Status
Paper mode only. Awaiting forward validation before live promotion.
