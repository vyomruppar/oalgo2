"""Ken French Data Library: daily Fama-French 3/5 factors and momentum (percent returns -> decimals)."""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from .http import HttpProvider

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {
    "ff3": "F-F_Research_Data_Factors_daily_CSV.zip",
    "ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "F-F_Momentum_Factor_daily_CSV.zip",
}


def parse_french_csv(text: str) -> pd.DataFrame:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith(","))
    rows = []
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    for ln in lines[start + 1:]:
        parts = [x.strip() for x in ln.split(",")]
        if len(parts) < len(cols) + 1 or not (parts[0].isdigit() and len(parts[0]) == 8):
            if rows:
                break
            continue
        rows.append(parts[: len(cols) + 1])
    df = pd.DataFrame(rows, columns=["date"] + cols)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date").apply(pd.to_numeric, errors="coerce")
    df = df.where(df > -99)  # -99.99 / -999 are missing-value codes
    return df / 100.0


class KenFrench:
    def __init__(self) -> None:
        self.http = HttpProvider("ken_french", rps=1.0)

    def _get(self, key: str) -> pd.DataFrame:
        raw = self.http.get(BASE + FILES[key], ttl_seconds=7 * 86400).content
        z = zipfile.ZipFile(io.BytesIO(raw))
        return parse_french_csv(z.read(z.namelist()[0]).decode("latin-1"))

    def factors(self) -> pd.DataFrame:
        """Columns: Mkt-RF, SMB, HML, RMW, CMA, RF, MOM (daily decimals)."""
        ff5 = self._get("ff5")
        mom = self._get("mom")
        mom.columns = ["MOM"]
        return ff5.join(mom, how="left")
