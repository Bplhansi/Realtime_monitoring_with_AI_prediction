from dataclasses import dataclass, field


@dataclass
class Config:
    limits: dict = field(default_factory=lambda: {"p95_ms": 400.0, "error_rate": 0.10})
    horizon: int = 30            # seconds ahead to forecast
    lateness: int = 1            # seconds a log line may arrive late and still count
    history: int = 120           # windows kept for the dashboard
    sustain: int = 2             # consecutive bad windows before an incident opens
    sustain_predicted: int = 3   # consecutive "will breach" windows before a watch opens
    predicted_within: int = 20   # only care about breaches this close (seconds)
    predict_min_fraction: float = 0.6  # ignore breach forecasts while the level is below this share of the limit
    resolve_after: int = 5       # consecutive clean windows before an incident resolves
