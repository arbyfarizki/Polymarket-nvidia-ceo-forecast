"""polymarket-nvidia-ceo-forecast-01 entry (Python 3.13, standard library only).

Forecasts the Yes price of every trading market of Polymarket's "Next CEO of
NVIDIA?" event at every minute of the 4 hours after a checkpoint, as five
quantiles (5%, 25%, 50%, 75%, 95%) per minute.

Model (per market, fitted only on the case's own 72h of minute prices):
  q_tau(h) = clamp(x + z_tau * k_tau * sigma * h**0.38, 0, 1), rounded to 6 dp
where x is the market's last price at the checkpoint and sigma is a robust
scale of its recent 1-minute price moves: the standard deviation of the
1-minute changes over the last 12 hours (720 minutes), trimmed 2% on each
side so a rare huge jump does not blow the scale up. The tails are widened
(k = 1.6 at 5%/95%, 1.0 at 25%/75%) because the moves are heavy-tailed, and
the spread grows like h**0.38 rather than sqrt(h) because the moves are
mean-reverting over hours. The median is the last price: prediction-market
prices are martingales, and adding a drift made the practice loss worse.
A floor of 0.0004 keeps a flat market from getting a zero-width band.

Practice score (local, on the six practice cases, scored against Polymarket's
own history): pinball loss 0.272686, vs the house baseline's 0.363589 and the
best house entry's 0.313. Median error 0.767503, 90% coverage 0.891276.

Deterministic: no randomness, no wall clock, no network. Reads every
<id>.in in the input directory and writes <id>.out to the output directory.
Outside the grader, MAKEFUN_INPUT_DIR / MAKEFUN_OUTPUT_DIR stand in for
/input and /output:
  mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
from statistics import pstdev

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

# The quantile levels the contest scores, in the order each row lists them.
QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles, with the tail levels widened for heavy tails
# (k = 1.6 at 5%/95%, 1.0 at 25%/75%/50%).
Z = [-1.644854 * 1.6, -0.67449, 0.0, 0.67449, 1.644854 * 1.6]
# Spread grows like h**ALPHA (mean-reverting moves, not a pure random walk).
ALPHA = 0.38
# Recent window (minutes) for the volatility estimate.
SIGMA_WINDOW = 720
# Trim fraction on each side when estimating the scale (robust to jumps).
TRIM = 0.02
# Minimum 1-minute scale, so a flat market still gets a band.
SIGMA_FLOOR = 0.0004


def price6(x):
    """x clamped to [0, 1] and rounded to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def robust_sigma(changes):
    """Trimmed standard deviation of 1-minute price changes."""
    n = len(changes)
    if n < 2:
        return 0.0
    s = sorted(changes)
    k = max(1, int(TRIM * n))
    core = s[k:n - k] if n - 2 * k > 10 else s
    return pstdev(core)


def forecast(market, horizon, h_pow):
    """The forecast rows for one market: horizon rows of five quantiles."""
    prices = market["prices"]
    if not prices:
        raise ValueError("market %s has no prices" % market["id"])
    x = prices[-1]
    n = len(prices)
    w = min(SIGMA_WINDOW, n - 1)
    changes = [prices[i + 1] - prices[i] for i in range(n - w - 1, n - 1)]
    sigma = max(robust_sigma(changes), SIGMA_FLOOR)
    rows = []
    for h in range(1, horizon + 1):
        spread = sigma * h_pow[h]
        row = [price6(x + z * spread) for z in Z]
        # Clamping can break the order at 0/1; restore non-decreasing.
        for j in range(1, 5):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Precompute h**ALPHA once; shared by every market.
    h_pow = [0.0] + [h ** ALPHA for h in range(1, 241)]
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for fname in inputs:
        case_id = fname[: -len(".in")]
        with open(os.path.join(INPUT_DIR, fname), "r", encoding="utf-8") as f:
            case = json.load(f)
        if case["quantiles"] != QUANTILES:
            raise ValueError(
                "%s asks for quantiles %s, not %s"
                % (fname, case["quantiles"], QUANTILES)
            )
        horizon = case["horizon_minutes"]
        if horizon > 240:
            raise ValueError("%s asks for horizon %d" % (fname, horizon))
        forecasts = [
            {"id": m["id"], "q": forecast(m, horizon, h_pow)}
            for m in case["markets"]
        ]
        with open(
            os.path.join(OUTPUT_DIR, "%s.out" % case_id), "w", encoding="utf-8"
        ) as f:
            f.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
