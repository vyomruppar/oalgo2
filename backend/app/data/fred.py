"""FRED macro series via the public CSV export (no API key)."""
from __future__ import annotations

import io

import pandas as pd

from .http import HttpProvider

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
SERIES = {"DGS10": "10-year Treasury yield (%)", "DGS3MO": "3-month Treasury yield (%)",
          "T10Y2Y": "10y minus 2y Treasury spread (pp)", "BAMLH0A0HYM2": "High-yield OAS (%)"}


def parse_fred_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    df.columns = ["date", "value"]
    s = pd.to_numeric(df["value"], errors="coerce")
    s.index = pd.to_datetime(df["date"])
    return s.dropna()


class Fred:
    def __init__(self) -> None:
        self.http = HttpProvider("fred", rps=1.0, timeout=60.0)

    def series(self, sid: str) -> pd.Series:
        return parse_fred_csv(self.http.get(URL.format(sid=sid), ttl_seconds=12 * 3600).content.decode())
