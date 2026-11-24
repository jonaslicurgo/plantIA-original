"""Species-confirmed public evidence from WCVP and Extension horticultural facts."""

from html import unescape
from http.client import HTTPException
import json
import os
import re
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from plantia.services.botanical_backbone import cached
from plantia.utils.taxon import normalize

KEW = "https://powo.science.kew.org"
NC = "https://plants.ces.ncsu.edu"
NC_LABEL = "NC State Extension"
KEW_LABEL = "Royal Botanic Gardens, Kew · WCVP · CC BY 4.0"
ASPCA = "https://www.aspca.org/pet-care/aspca-poison-control/toxic-and-non-toxic-plants/"
_LIMIT = Lock()
_next_request = {}
IPNI = re.compile(r"urn:lsid:ipni\.org:names:[0-9]+-[0-9]+")

PRIORITIES = {
    "Monstera deliciosa": "Araceae",
    "Nerium oleander": "Apocynaceae",
    "Ricinus communis": "Euphorbiaceae",
    "Aloe vera": "Asphodelaceae",
    "Ocimum basilicum": "Lamiaceae",
}
PRIORITY_FAMILIES = {normalize(name): normalize(family) for name, family in PRIORITIES.items()}

# These summaries stay attached to the exact accepted species and cited facts.
SAFETY = {
    "monstera deliciosa": {
        "human_toxicity": ("monstera_human", "nc"),
        "animal_toxicity": ("pets_toxic", "cutleaf-philodendron"),
        "toxic_parts": ("monstera_parts", "nc"),
        "exposure": ("monstera_contact", "nc"),
    },
    "nerium oleander": {
        "human_toxicity": ("oleander_human", "nc"),
        "animal_toxicity": ("pets_toxic", "oleander"),
        "toxic_parts": ("oleander_parts", "nc"),
    },
    "ricinus communis": {
        "human_toxicity": ("ricinus_human", "nc"),
        "animal_toxicity": ("pets_toxic", "nc"),
        "toxic_parts": ("ricinus_parts", "nc"),
    },
    "aloe vera": {"animal_toxicity": ("pets_toxic", "aloe"), "human_toxicity": ("aloe_human", "nc")},
    "ocimum basilicum": {"animal_toxicity": ("basil_pets", "basil")},
}


# Standard scientific names and original short summaries backed by species-level entries.
HORTICULTURAL_NOTES = {
    "nerium oleander": {"pests": "Aphididae · Pseudococcidae", "diseases": "Armillaria spp. · Verticillium spp."},
    "ricinus communis": {"pests": "Tetranychidae", "fertilization": "enrichment.castor_fertilization"},
    "aloe vera": {"pests": "Pseudococcidae · Aphididae"},
    "ocimum basilicum": {"pests": "Aphididae · Popillia japonica", "diseases": "Fusarium spp. · Peronospora belbahrii"},
}
EXTRA_FIELDS = {
    "taxonomy": ("growth_form", "biome", "introduced"),
    "garden": ("drainage", "soil", "moisture", "watering", "propagation", "fertilization", "pests", "diseases"),
    "risks": ("contraindications", "allergies"),
}


# Only short factual classifications are transformed. Third-party descriptions,
# photographs, directions and medical prose are excluded from this adapter.
EXTENSION_FIELDS = {
    "Light": {"light": {"Full sun": "sun", "Partial Shade": "shade", "Dappled Sunlight": "dappled",
                         "Deep shade": "deep_shade"}},
    "Soil Drainage": {"drainage": {"Good Drainage": "drainage_value"},
                      "moisture": {"Moist": "moist", "Occasionally Dry": "dry"},},
    "Soil Texture": {"soil": {"High Organic Matter": "organic", "Loam": "loam", "Sand": "sand", "Clay": "clay"}},
    "Recommended Propagation Strategy": {"propagation": {"Seed": "seed", "Stem Cutting": "cutting",
                                                          "Layering": "layering", "Division": "division"}},
    "Attracts": {"pollinators": {"Bees": "bees", "Butterflies": "butterflies", "Hummingbirds": "hummingbirds"}},
}


def _download(url, maximum, content_type):
    host = urlsplit(url).hostname
    with _LIMIT:
        now = monotonic()
        start = max(now, _next_request.get(host, 0))
        if start - now > 3:
            return None
        _next_request[host] = start + 1
    sleep(start - now)
    request = Request(url, headers={"User-Agent": "PLANET-IA Botanical Catalog (https://github.com/jonaslicurgo/plantIA-original)",
                                    "Accept": content_type})
    try:
        with urlopen(request, timeout=4) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != host:
                return None
            content = response.read(maximum + 1)
        return content if len(content) <= maximum else None
    except (OSError, HTTPException):
        return None


def _json(url):
    payload = _download(url, 700_000, "application/json")
    try:
        value = json.loads(payload) if payload else None
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError):
        return {}


def _kew(name, family):
    search = _json(KEW + "/api/2/search?" + urlencode({"q": name}))
    hits = {row.get("fqId") for row in search.get("results", [])
            if row.get("accepted") is True and str(row.get("rank")).lower() == "species"
            and row.get("kingdom") == "Plantae" and normalize(row.get("name") or "") == normalize(name)
            and (not family or normalize(row.get("family") or "") == normalize(family))}
    if len(hits) != 1:
        return None
    identifier = hits.pop()
    if not isinstance(identifier, str) or not IPNI.fullmatch(identifier):
        return None
    detail = _json(f"{KEW}/api/2/taxon/{identifier}?fields=distribution")
    if (detail.get("fqId") != identifier or detail.get("taxonomicStatus") != "Accepted"
            or str(detail.get("rank")).lower() != "species" or normalize(detail.get("name") or "") != normalize(name)
            or not str(detail.get("source", "")).startswith("wcvp:")):
        return None
    result = {"url": f"{KEW}/taxon/{identifier}"}
    for field in ("lifeform", "climate"):
        value = detail.get(field)
        if isinstance(value, str) and 0 < len(value) <= 100:
            result[field] = value
    distribution = detail.get("distribution") or {}
    for role in ("natives", "introduced"):
        result[role] = list(dict.fromkeys(
            row["name"][:90] for row in distribution.get(role, []) if isinstance(row.get("name"), str)
        ))[:25]
    return result


def _slug(name):
    pieces = normalize(name).split()
    if len(pieces) == 2 and all(re.fullmatch("[a-z-]+", piece) for piece in pieces):
        return "-".join(pieces)
    return None


def _extension(name, url):
    content = _download(url, 600_000, "text/html")
    if not content:
        return None
    html = content.decode("utf-8", errors="replace")
    heading = re.search(r"<h1\b[^>]*>\s*<em>([^<]+)</em>", html, re.I)
    if not heading or normalize(unescape(heading[1])) != normalize(name):
        return None
    result = {}
    for label, fields in EXTENSION_FIELDS.items():
        block = re.search(rf"<dt\b[^>]*>\s*{re.escape(label)}:?\s*</dt>(.*?)(?=<dt\b|</dl>)", html, re.I | re.S)
        if not block:
            continue
        values = [re.sub(r"\s*\(.*", "", unescape(val).strip()).casefold() for val in re.findall(
            r'<span class="detail_display_attribute">([^<]+)</span>', block[1])]
        for field, standard in fields.items():
            found = [key for original, key in standard.items() if original.casefold() in values]
            if found:
                result[field] = found
    return result or None


def facts(item, locale, translate):
    name = item["name"]
    normalized = normalize(name)
    family = item.get("family", "")
    expected = PRIORITY_FAMILIES.get(normalized)
    if expected and normalize(family) != expected:
        return []
    slug = _slug(name)
    nc_url = f"{NC}/plants/{slug}/" if slug else None
    entries = []

    def add(field, value, publisher, url):
        entries.append((field, value, (publisher, url)))

    if locale == "pt-BR" and normalized == "monstera deliciosa" and normalize(item.get("family", "")) == "araceae":
        add("common_name", "Costela-de-adão", "GBIF · Catalogue of Life",
            "https://api.gbif.org/v1/species/2868241/vernacularNames?limit=100")
    for field, (key, publisher) in SAFETY.get(normalized, {}).items():
        if publisher == "nc":
            add(field, translate(f"enrichment.{key}"), NC_LABEL, nc_url)
        else:
            add(field, translate(f"enrichment.{key}"), "ASPCA Poison Control", ASPCA + publisher)
    for field, value in HORTICULTURAL_NOTES.get(normalized, {}).items():
        add(field, translate(value) if value.startswith("enrichment.") else value, NC_LABEL, nc_url)
    if os.getenv("PLANET_BOTANICAL_ENRICHMENT", "1") == "0":
        return entries

    kew = cached(f"wcvp:v1:{normalized}:{family}", lambda: _kew(name, family), 30 * 86400)
    if kew:
        for field, key in (("growth_form", "lifeform"), ("biome", "climate"),
                           ("origin", "natives"), ("introduced", "introduced")):
            value = kew.get(key)
            if value:
                add(field, " · ".join(value) if isinstance(value, list) else value, KEW_LABEL, kew["url"])
    if nc_url:
        extension = cached(f"extension:v1:{normalized}", lambda: _extension(name, nc_url), 30 * 86400)
        for field, values in (extension or {}).items():
            phrases = [translate(("library." if key in {"sun", "shade", "drainage_value"}
                                  else "enrichment.") + key) for key in values]
            add(field, " · ".join(phrases), NC_LABEL, nc_url)
        if normalized in {"monstera deliciosa", "aloe vera"} and extension:
            add("watering", translate("enrichment.water_monstera" if normalized == "monstera deliciosa"
                                     else "enrichment.water_aloe"), NC_LABEL, nc_url)
    return entries
