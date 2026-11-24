"""Indexed read-only GBIF taxonomy and bounded enrichment from fixed public endpoints."""

import hashlib
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock
from time import time
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import text

from plantia.config import APP_DATA_DIR
from plantia.database import get_engine

DATASET = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
GBIF = "https://api.gbif.org/v1/"
LOCKS = tuple(Lock() for _ in range(32))


@contextmanager
def index():
    path = Path(os.getenv("PLANET_BOTANICAL_INDEX", str(APP_DATA_DIR / "botanical.sqlite"))).resolve()
    if not path.is_file():
        yield None
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        yield db


def taxon_key(species_id):
    match = re.fullmatch(r"gbif-([0-9]{1,10})", species_id)
    return int(match[1]) if match else None


def query(q, limit, offset, favorites=None):
    with index() as db:
        if db is None:
            return 0, []
        parts = re.findall(r"[^\W_]+", q, flags=re.UNICODE)
        if q and not parts:
            return 0, []
        clauses = ["t.rank='SPECIES'", "t.reviewed IS NULL"]
        params = {}
        candidates = "taxa t"
        if parts:
            candidates += (" JOIN (SELECT DISTINCT n.taxon FROM names_search s "
                           "JOIN names n ON n.rowid=s.rowid WHERE names_search MATCH :query) m ON m.taxon=t.id")
            params["query"] = " AND ".join(f'"{part}"*' for part in parts[:12])
        if favorites is not None:
            clauses.append("t.id IN (SELECT value FROM json_each(:favorites))")
            params["favorites"] = json.dumps(favorites)
        where = " AND ".join(clauses)
        if not parts and favorites is None:
            total = int(db.execute("SELECT value FROM metadata WHERE key='species'").fetchone()[0])
        else:
            total = db.execute(f"SELECT count(*) FROM {candidates} WHERE {where}", params).fetchone()[0]
        items = db.execute(f"SELECT t.id,t.name FROM {candidates} WHERE {where} ORDER BY t.id LIMIT :limit OFFSET :offset",
                           {**params, "limit": limit, "offset": offset}).fetchall() if limit else []
        return total, items


def lookup(species_id):
    key = taxon_key(species_id)
    if key is None:
        return None
    with index() as db:
        if db is None:
            return None
        row = db.execute("""SELECT t.*,f.name AS family_name FROM taxa t LEFT JOIN taxa f ON t.family=f.id
            WHERE t.id=? AND t.rank='SPECIES'""", (key,)).fetchone()
        if row is None:
            return None
        synonyms = [item[0] for item in db.execute("""SELECT DISTINCT name FROM names
            WHERE taxon=? AND kind='synonym' ORDER BY name LIMIT 20""", (key,))]
        lineage = [item[0] for item in db.execute("""WITH RECURSIVE ancestors(id,parent,name,depth) AS (
            SELECT id,parent,name,0 FROM taxa WHERE id=?
            UNION ALL SELECT t.id,t.parent,t.name,a.depth+1 FROM taxa t JOIN ancestors a ON t.id=a.parent
            WHERE a.depth<12) SELECT name FROM ancestors ORDER BY depth DESC""", (key,))]
    return {"id": species_id, "gbif": key, "name": row["name"], "family": row["family_name"] or "",
            "reviewed": row["reviewed"], "scientific": row["scientific"], "aliases": synonyms, "lineage": lineage, "labels": {},
            "source": f"https://www.gbif.org/species/{key}", "categories": []}


def _request(path, params=None):
    url = GBIF + path + ("?" + urlencode(params, doseq=True) if params else "")
    req = Request(url, headers={"User-Agent": "PLANET-IA botanical library/1.0"})
    try:
        with urlopen(req, timeout=4) as response:
            result = json.loads(response.read(512_000))
        return result if isinstance(result, dict) else None
    except (OSError, ValueError, URLError):
        return None


def cached(key, fetch, ttl=604800):
    with LOCKS[hash(key) % len(LOCKS)]:
        with get_engine().connect() as db:
            payload = db.execute(text("SELECT payload FROM botanical_source_cache WHERE key=:key AND expires>:now"),
                                 {"key": key, "now": int(time())}).scalar()
        if payload is not None:
            return json.loads(payload)
        result = fetch()
        payload = json.dumps(result)
        if len(payload.encode()) > 8192:
            return result
        with get_engine().begin() as db:
            now = int(time())
            db.execute(text("DELETE FROM botanical_source_cache WHERE expires<=:now"), {"now": now})
            db.execute(text("""INSERT INTO botanical_source_cache VALUES (:key,:payload,:expires)
                ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires=excluded.expires"""),
                {"key": key, "payload": payload, "expires": now + (ttl if result else 900)})
            db.execute(text("""DELETE FROM botanical_source_cache WHERE key IN
                (SELECT key FROM botanical_source_cache ORDER BY expires DESC LIMIT -1 OFFSET 20000)"""))
        return result


def remote_names(q, page):
    with index() as db:
        if db is None or len(q) < 3 or not all(c.isalpha() or c in " -×´’'" for c in q):
            return 0, []
    offset = (page - 1) * 20
    if offset >= 100_000:
        return 0, []
    def fetch():
        raw = _request("species/search", {"q": q, "qField": "VERNACULAR", "datasetKey": DATASET,
            "higherTaxonKey": 6, "rank": "SPECIES", "status": "ACCEPTED", "limit": 20, "offset": offset})
        if raw is None:
            return None
        return {"count": raw.get("count", 0), "results": [
            {"key": row.get("key"), "vernacularNames": [
                {"language": label.get("language") or "", "vernacularName": label["vernacularName"][:85]}
                for label in row.get("vernacularNames", [])[:3] if isinstance(label.get("vernacularName"), str)
            ]} for row in raw.get("results", [])
        ]}
    term_hash = hashlib.sha256(q.casefold().encode()).hexdigest()
    result = cached(f"names:{term_hash}:{page}", fetch, 86400) or {}
    matches = []
    for row in result.get("results", []):
        key = row.get("key")
        if not isinstance(key, int):
            continue
        item = lookup(f"gbif-{key}")
        if item and not item["reviewed"]:
            item["labels"] = {str(entry.get("language", "")).lower(): entry["vernacularName"][:150]
                              for entry in row.get("vernacularNames", [])
                              if isinstance(entry.get("vernacularName"), str)}
            matches.append(item)
    return result.get("count", 0), matches


def _media_license(value):
    match = re.fullmatch(r"https?://creativecommons\.org/(?:(licenses/by(?:-sa)?/([234]\.0))|(publicdomain/zero/1\.0))/?",
                         value or "")
    if not match:
        return None
    path = match[1] or match[3]
    name = "CC0 1.0" if match[3] else f"CC {'BY-SA' if 'by-sa' in path else 'BY'} {match[2]}"
    return name, f"https://creativecommons.org/{path}/"


def _trusted_image(url):
    if not isinstance(url, str) or len(url) > 1500:
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.port in (None, 443) and parsed.username is None
                and parsed.hostname in {"upload.wikimedia.org", "thumb.wikimedia.org",
                    "inaturalist-open-data.s3.amazonaws.com", "static.inaturalist.org"})
    except ValueError:
        return False


def licensed_photo(result):
    for occurrence in result.get("results", []):
        key = occurrence.get("key")
        if not isinstance(key, int):
            continue
        for media in occurrence.get("media", []):
            license_info = _media_license(media.get("license"))
            author = media.get("creator") or media.get("rightsHolder")
            url = media.get("identifier")
            if (media.get("type") == "StillImage" and license_info and isinstance(author, str) and author.strip() and _trusted_image(url)):
                name, license_url = license_info
                return {"url": url, "source": f"https://www.gbif.org/occurrence/{key}",
                        "author": author.strip()[:250], "license": name, "license_url": license_url}
    return None


def enrich(key):
    def fetch():
        names = _request(f"species/{key}/vernacularNames", {"limit": 50}) or {}
        locations = _request("occurrence/search", {"taxon_key": key, "limit": 0, "facet": "country",
                                                  "facetLimit": 24}) or {}
        media = _request("occurrence/search", {"taxon_key": key, "limit": 15, "media_type": "StillImage",
                                              "license": ["CC0_1_0", "CC_BY_4_0"]}) or {}
        labels = {}
        for row in names.get("results", []):
            label, language = row.get("vernacularName"), row.get("language")
            if isinstance(label, str) and isinstance(language, str):
                labels.setdefault(language.lower(), label[:150])
        countries = [row["name"] for facet in locations.get("facets", []) if facet.get("field") == "COUNTRY"
                     for row in facet.get("counts", []) if re.fullmatch(r"[A-Z]{2}", row.get("name", "")) and row["name"] != "ZZ"]
        payload = {"labels": labels, "countries": countries, "photo": licensed_photo(media)}
        return payload if any(payload.values()) else None
    return cached(f"species:{key}", fetch) or {}
