"""Power for the M6–M8 reserve test, round 3's way (RESERVE_CRITERIA_R3 §6).

Target n = ceil(1.3 * ((z_0.975 + z_0.90) * SD / delta)^2) clusters; achieved power at the sealed
n = Phi(delta * sqrt(n) / SD - z_0.975). SD is the per-cluster gain spread on DEV (method minus
the better baseline); delta is the DEV gain, floored at 0.03.
"""
import math

from scipy.stats import norm


def target_n(sd, delta):
    d = max(abs(delta), 0.03)
    return math.ceil(1.3 * ((norm.ppf(0.975) + norm.ppf(0.90)) * sd / d) ** 2)


def achieved(sd, delta, n):
    d = max(abs(delta), 0.03)
    return float(norm.cdf(d * math.sqrt(n) / sd - norm.ppf(0.975))) if sd > 0 else float("nan")
