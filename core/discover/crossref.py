import time
import requests
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterator, List, Optional, Any

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class CrossrefConfig:
    mailto: Optional[str] = None
    timeout_sec: int = 30
    per_page: int = 200
    polite_sleep_sec: float = 1.0


class CrossrefClient:
    """
    Discover layer: query Crossref for recent works of a journal (by ISSN).
    - Uses cursor pagination (robust for >1000 results)
    - Retries on transient errors (429/5xx)
    - Normalizes output fields
    """
    BASE = "https://api.crossref.org"

    def __init__(self, cfg: CrossrefConfig):
        self.cfg = cfg
        self.sess = requests.Session()

        retry = Retry(
            total=6,
            backoff_factor=1.0,  # 1s,2s,4s...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.sess.mount("https://", adapter)
        self.sess.mount("http://", adapter)

        ua = "paperbot/0.1 (discover; +https://github.com/your/repo)"
        if cfg.mailto:
            ua += f" mailto:{cfg.mailto}"
        self.sess.headers.update({"User-Agent": ua})

    def iter_journal_works(
            self,
            issn: str,
            from_date: date,
            until_date: date,
            *,
            only_journal_articles: bool = True,
            select_fields: Optional[List[str]] = None,
            max_items: Optional[int] = None,
            date_filter: str = "pub-date",  # ✅ 新增：pub-date / update-date / index-date / deposit-date / created-date
    ) -> Iterator[Dict[str, Any]]:
        """
        Yields raw Crossref items (message.items).
        """
        endpoint = f"{self.BASE}/works"

        # Crossref filters: from-pub-date / until-pub-date
        date_filter = (date_filter or "pub-date").strip().lower()
        issn = issn.replace("-", "").strip()
        filters = [
            f"from-{date_filter}:{from_date.isoformat()}",
            f"until-{date_filter}:{until_date.isoformat()}",
            f"issn:{issn}",
        ]
        if only_journal_articles:
            filters.append("type:journal-article")

        params = {
            "filter": ",".join(filters),
            "rows": int(self.cfg.per_page),
            "cursor": "*",  # start cursor
        }

        if self.cfg.mailto:
            params["mailto"] = self.cfg.mailto

        if select_fields is None:
            # Keep it lightweight; add/remove as you need
            select_fields = [
                "DOI", "title", "URL", "author", "container-title", "ISSN",
                "published-online", "published-print", "issued", "created",
                "subject", "type", "publisher",
                "link",  # ← 加这一项
            ]
        params["select"] = ",".join(select_fields)

        fetched = 0
        last_cursor = None

        while True:
            resp = self.sess.get(endpoint, params=params, timeout=self.cfg.timeout_sec)
            if resp.status_code >= 400:
                # retry handled by adapter; if still failing, raise with context
                raise RuntimeError(f"Crossref error {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            msg = data.get("message", {})
            items = msg.get("items", []) or []
            next_cursor = msg.get("next-cursor")

            if not items:
                break

            for it in items:
                yield it
                fetched += 1
                if max_items is not None and fetched >= max_items:
                    return

            # Polite sleep to avoid hammering
            time.sleep(self.cfg.polite_sleep_sec)

            # Cursor pagination
            if not next_cursor or next_cursor == last_cursor:
                break
            last_cursor = next_cursor
            params["cursor"] = next_cursor


def _pick_date_parts(item: Dict[str, Any], key: str) -> Optional[List[int]]:
    """Crossref date-parts parsing helper."""
    obj = item.get(key)
    if not isinstance(obj, dict):
        return None
    parts = obj.get("date-parts")
    if not parts or not isinstance(parts, list) or not parts[0]:
        return None
    return parts[0]


def _best_pub_date(item: Dict[str, Any]) -> Optional[str]:
    """
    Prefer published-online > published-print > issued > created
    Return ISO date string (YYYY-MM-DD).
    """
    for k in ["published-online", "published-print", "issued", "created"]:
        parts = _pick_date_parts(item, k)
        if parts:
            y = parts[0]
            m = parts[1] if len(parts) >= 2 else 1
            d = parts[2] if len(parts) >= 3 else 1
            try:
                return date(int(y), int(m), int(d)).isoformat()
            except Exception:
                continue
    return None


def normalize_crossref_item(raw: Dict[str, Any], *, journal_name_fallback: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalize Crossref raw item to your internal schema for later stages.
    """
    doi = (raw.get("DOI") or "").strip()
    title_list = raw.get("title") or []
    title = title_list[0].strip() if isinstance(title_list, list) and title_list else ""

    container = raw.get("container-title") or []
    journal = container[0].strip() if isinstance(container, list) and container else (journal_name_fallback or "")

    authors = []
    for a in (raw.get("author") or []):
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        name = (given + " " + family).strip() if (given or family) else ""
        if name:
            authors.append(name)

    return {
        "doi": doi,
        "title": title,
        "journal": journal,
        "publisher": (raw.get("publisher") or "").strip(),
        "published_date": _best_pub_date(raw),
        "url": (raw.get("URL") or "").strip(),
        "issn": raw.get("ISSN") or [],
        "subjects": raw.get("subject") or [],
        "type": (raw.get("type") or "").strip(),
        "authors": authors,
        "raw": raw,  # 可选：保留原始元数据方便调试
    }


def discover_recent_papers_for_journal(
    client: CrossrefClient,
    journal_cfg: Dict[str, Any],
    from_date: date,
    until_date: date,
) -> List[Dict[str, Any]]:
    jname = journal_cfg.get("name")

    # ✅ 支持多 ISSN：crossref_issns 优先；否则回退到 crossref_issn/issn_print
    issns = journal_cfg.get("crossref_issns")
    if not issns:
        issns = []
        if journal_cfg.get("crossref_issn"):
            issns.append(journal_cfg["crossref_issn"])
        if journal_cfg.get("issn_print"):
            issns.append(journal_cfg["issn_print"])
        # 去重保持顺序
        seen = set()
        issns = [x for x in issns if x and not (x in seen or seen.add(x))]

    date_filter = journal_cfg.get("discover_date_filter", "pub-date")

    by_doi: Dict[str, Dict[str, Any]] = {}

    for issn in issns:
        for raw in client.iter_journal_works(
            issn,
            from_date,
            until_date,
            only_journal_articles=True,
            date_filter=date_filter,
        ):
            norm = normalize_crossref_item(raw, journal_name_fallback=jname)
            if norm["doi"]:
                by_doi[norm["doi"]] = norm

    return list(by_doi.values())