import math
from collections import deque
from dataclasses import dataclass


@dataclass
class Reading:
    value: float
    expected: float
    sigma: float
    z: float
    anomaly: bool


class HoltDetector:
    """Holt's linear smoothing: predicts the next value, forecasts ahead, flags outliers.

    A point is anomalous when its residual exceeds z_threshold standard deviations.
    While readings are anomalous the baseline is frozen, so a spike or an outage cannot
    teach the model that it is normal. If the shift lasts more than `max_freeze` steps it
    is accepted as the new normal and the baseline resets to it.
    """

    def __init__(self, alpha=0.3, beta=0.1, z_threshold=4.0, warmup=20,
                 min_sigma=1.0, window=60, direction="both", max_freeze=60):
        if direction not in ("both", "up"):
            raise ValueError("direction must be 'both' or 'up'")
        self.alpha, self.beta, self.z_threshold = alpha, beta, z_threshold
        self.warmup, self.min_sigma, self.direction = warmup, min_sigma, direction
        self.max_freeze = max_freeze
        self._frozen = 0
        self.level = None
        self.trend = 0.0
        self.n = 0
        self._resid = deque(maxlen=window)

    @property
    def sigma(self) -> float:
        if len(self._resid) < 5:
            return self.min_sigma
        mean = sum(self._resid) / len(self._resid)
        var = sum((r - mean) ** 2 for r in self._resid) / len(self._resid)
        return max(self.min_sigma, math.sqrt(var))

    def update(self, x: float) -> Reading:
        self.n += 1
        if self.level is None:
            self.level = x
            return Reading(x, x, self.min_sigma, 0.0, False)
        expected = self.level + self.trend
        sigma = self.sigma
        resid = x - expected
        z = resid / sigma
        outlier = abs(z) > self.z_threshold if self.direction == "both" else z > self.z_threshold
        anomaly = self.n > self.warmup and outlier
        if anomaly:
            self._frozen += 1
            if self._frozen > self.max_freeze:
                self.level, self.trend, self._frozen = x, 0.0, 0
                self._resid.clear()
            return Reading(x, expected, sigma, z, True)
        self._frozen = 0
        self._resid.append(resid)
        new_level = self.alpha * x + (1 - self.alpha) * expected
        self.trend = self.beta * (new_level - self.level) + (1 - self.beta) * self.trend
        self.level = new_level
        return Reading(x, expected, sigma, z, anomaly)

    def forecast(self, horizon: int) -> list:
        """Mean and 95% range for each of the next `horizon` steps."""
        if self.level is None:
            return []
        s = self.sigma
        out = []
        for k in range(1, horizon + 1):
            m = self.level + self.trend * k
            w = 1.96 * s * math.sqrt(k)
            out.append({"m": round(m, 3), "lo": round(m - w, 3), "hi": round(m + w, 3)})
        return out

    def steps_to_exceed(self, limit: float, horizon: int):
        """First step in the forecast where the mean passes `limit`, else None."""
        if self.level is None or self.n <= self.warmup:
            return None
        for k in range(1, horizon + 1):
            if self.level + self.trend * k > limit:
                return k
        return None
