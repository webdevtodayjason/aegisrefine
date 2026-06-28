"""Real run statistics — these feed the certificate and the on-page numbers. No invented figures."""
from dataclasses import dataclass


@dataclass
class Stats:
    rows_in: int = 0
    rows_out: int = 0
    dupes_removed: int = 0
    pii_masked: int = 0
    dropped_invalid: int = 0

    @property
    def noise_reduced_pct(self) -> float:
        if not self.rows_in:
            return 0.0
        return round(100 * (self.rows_in - self.rows_out) / self.rows_in, 1)

    def as_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "dupes_removed": self.dupes_removed,
            "pii_masked": self.pii_masked,
            "dropped_invalid": self.dropped_invalid,
            "noise_reduced_pct": self.noise_reduced_pct,
        }
