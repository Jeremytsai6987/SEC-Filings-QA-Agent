import json
import time
import pathlib
import requests
from typing import Optional, Dict

class CompanyMeta:
    """Structured metadata for a public company"""

    def __init__(
        self,
        ticker: str,
        cik: str,
        name: str,
        sic: Optional[str] = None,
    ):
        self.ticker = ticker.upper()
        self.cik = str(cik).zfill(10)
        self.name = name
        self.sic = sic



class CompanyResolver:
    """
    Resolves ticker or company name to CompanyMeta using:
    - SEC's company_tickers.json file
    - Local caching for performance
    """

    def __init__(
        self,
        cache_path: str = "company_cache.json",
        company_file: str = "company_tickers.json"
    ):
        self.cache_path = pathlib.Path(cache_path)
        self.company_file = pathlib.Path(company_file)
        self.cache: Dict[str, dict] = self._load_cache()
        self.company_data: Dict[str, dict] = self._load_company_file()
        self.name_to_ticker: Dict[str, str] = self._build_name_index()

    #  Cache Handling
    def _load_cache(self) -> Dict[str, dict]:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text())
        return {}

    def _save_cache(self):
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2))

    #  Company File Handling
    def _load_company_file(self) -> Dict[str, dict]:
        if self.company_file.exists():
            return json.loads(self.company_file.read_text())
        return {}

    def _build_name_index(self) -> Dict[str, str]:
        """
        Builds a lowercase company name → ticker mapping.
        Also handles basic name shortening (e.g., "Apple Inc." → "Apple").
        """
        index = {}
        for _, row in self.company_data.items():
            ticker = row.get("ticker", "").upper()
            title = row.get("title", "")
            if not ticker or not title:
                continue

            name = title.lower().strip()
            index[name] = ticker

            #  Index simplified versions (remove suffixes)
            for suffix in [" inc.", " inc", " corp.", " corp", " ltd.", " ltd"]:
                if name.endswith(suffix):
                    short = name.replace(suffix, "").strip()
                    index[short] = ticker
        return index


    #  Ticker Resolution
    def _resolve_by_ticker(self, t: str) -> Optional[CompanyMeta]:
        """
        Resolve company by exact ticker symbol (case-insensitive).
        Uses cache and fallback to static file.
        """
        t = t.upper()

        # Use cache if recent
        if t in self.cache and time.time() - self.cache[t].get("_ts", 0) < 86400:
            d = self.cache[t]
            return CompanyMeta(**{k: d[k] for k in ["ticker", "cik", "name", "sic"] if k in d})

        # Look up in static file
        for _, row in self.company_data.items():
            if row.get("ticker", "").upper() == t:
                meta = CompanyMeta(
                    ticker=t,
                    cik=str(row.get("cik", "")),
                    name=row.get("title", ""),
                    sic=str(row.get("sic", "")) if row.get("sic") else None
                )

                # Cache metadata
                self.cache[t] = {
                    "ticker": meta.ticker,
                    "cik": meta.cik,
                    "name": meta.name,
                    "sic": meta.sic,
                    "_ts": time.time(),
                }
                self._save_cache()
                return meta
        return None

    # Public Interface
    def resolve(self, identifier: str) -> Optional[CompanyMeta]:
        """
        Resolve either a ticker or fuzzy company name (e.g., 'Apple').
        """
        identifier = identifier.strip()

        # Try exact ticker match
        meta = self._resolve_by_ticker(identifier.upper())
        if meta:
            return meta

        # Try fuzzy name match
        alt = self.name_to_ticker.get(identifier.lower())
        if alt:
            return self._resolve_by_ticker(alt)

        return None
