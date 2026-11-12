"""Mid-vs-Price signal bands.

Mid vs Price = (Mid - Price) / Price. Positive = trading below fair value (upside).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

NO_VALUATION = "No valuation"


@dataclass(frozen=True)
class BandThresholds:
    strong_buy: float = 0.30   # >= +30%
    add: float = 0.10          # +10% .. +30%
    trim: float = -0.10        # -25% .. -10%
    sell: float = -0.25        # <= -25%

    def validate(self) -> None:
        if not (self.strong_buy > self.add > self.trim > self.sell):
            raise ValueError("Thresholds must satisfy Strong Buy > Add > Trim > Sell")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "BandThresholds":
        if not d:
            return cls()
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


# name -> (background, text, short meaning). Explicit text colour keeps it legible in dark mode.
BANDS: dict[str, tuple[str, str, str]] = {
    "Strong Buy": ("#1e7b34", "#ffffff", "Obvious buy / add"),
    "Add": ("#b7e1b5", "#10301a", "Accumulate"),
    "Hold": ("#f1f1ec", "#2b2b2b", "Fairly valued"),
    "Trim": ("#f6c2bd", "#4a1410", "Trim / take some profit"),
    "Sell": ("#c0392b", "#ffffff", "Sell / take profit"),
    NO_VALUATION: ("#8a8a8a", "#ffffff", "Needs research"),
}
BAND_ORDER = list(BANDS)


def mid_vs_price(mid: float | None, price: float | None) -> float | None:
    if mid is None or price is None or price <= 0 or mid != mid or price != price:
        return None
    return mid / price - 1.0


def classify(gap: float | None, t: BandThresholds = BandThresholds()) -> str:
    if gap is None or gap != gap:
        return NO_VALUATION
    if gap >= t.strong_buy:
        return "Strong Buy"
    if gap >= t.add:
        return "Add"
    if gap > t.trim:
        return "Hold"
    if gap > t.sell:
        return "Trim"
    return "Sell"
