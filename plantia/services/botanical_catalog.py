"""Versioned public botanical evidence, separate from personal identifications."""

from pathlib import Path
import json

from sqlalchemy import text

from plantia.database import get_engine
from plantia.services import botanical_backbone as backbone
from plantia.services.botany import FILTERS, GROUPS, SOURCES, SPECIES
from plantia.utils.taxon import normalize

CATALOG = {
    item["id"]: item
    for item in json.loads((Path(__file__).parents[1] / "data/botanical_catalog.json").read_text(encoding="utf-8"))
}
CATEGORIES = FILTERS + ("skin", "hair", "tree", "flower", "fruit", "herb", "cactus", "succulent", "foliage")
PAGE_SIZE = 20


def common_name(item, locale):
    names = item["labels"]
    tag = locale.split("-")[0]
    iso3 = {"pt": "por", "en": "eng", "es": "spa", "fr": "fra", "de": "deu", "it": "ita",
            "hi": "hin", "id": "ind", "ar": "ara", "ja": "jpn", "ko": "kor", "zh": "zho"}
    return (names.get(locale.lower()) or names.get(tag) or names.get(iso3[tag])
            or names.get("en") or names.get("eng") or item["name"])


def categories(item):
    return set(item["categories"]) | SPECIES.get(item["name"].lower(), {}).keys()


def favorite_ids(owner):
    with get_engine().connect() as db:
        return set(db.execute(text("SELECT species_id FROM botanical_favorites WHERE account_id=:owner"),
                              {"owner": owner}).scalars())


def set_favorite(owner, species_id, favorite):
    params = {"owner": owner, "species": species_id}
    with get_engine().begin() as db:
        if favorite:
            db.execute(text("INSERT OR IGNORE INTO botanical_favorites VALUES (:owner,:species)"), params)
        else:
            db.execute(text("DELETE FROM botanical_favorites WHERE account_id=:owner AND species_id=:species"), params)


def search(owner, locale, q, category, favorites, page):
    term = normalize(q)
    saved = favorite_ids(owner)
    matches = []
    for species_id, item in CATALOG.items():
        if (favorites and species_id not in saved) or (category and category not in categories(item)):
            continue
        names = (item["name"], *item["labels"].values(), *item.get("aliases", ()))
        if term and not any(term in normalize(name) for name in names):
            continue
        matches.append({"id": species_id, "scientific_name": item["name"],
                        "common_name": common_name(item, locale), "favorite": species_id in saved})
    matches.sort(key=lambda row: (normalize(row["common_name"]), row["scientific_name"]))
    offset = (page - 1) * PAGE_SIZE
    curated = matches[offset:offset + PAGE_SIZE]
    total = len(matches)
    if not category:
        keys = [key for value in saved if (key := backbone.taxon_key(value)) is not None] if favorites else None
        external, indexed = backbone.query(q, PAGE_SIZE - len(curated), max(0, offset - total), keys)
        if term and not total and not external and not favorites:
            external, remote = backbone.remote_names(q.strip(), page)
            curated.extend({"id": item["id"], "scientific_name": item["name"],
                            "common_name": common_name(item, locale), "favorite": item["id"] in saved,
                            "kind": "taxonomy"} for item in remote)
        else:
            curated.extend({"id": f"gbif-{row['id']}", "scientific_name": row["name"], "common_name": row["name"],
                            "favorite": f"gbif-{row['id']}" in saved, "kind": "taxonomy"} for row in indexed)
        total += external
    return {"items": curated, "total": total, "page": page,
            "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE}


def find(species_id):
    return CATALOG.get(species_id) or backbone.lookup(species_id)


def profile(item, owner, locale, tr):
    rows = {}
    gbif_key = item.get("gbif")
    if gbif_key:
        item = {**item, **backbone.enrich(gbif_key)}
    source = ("GBIF" if item["source"].startswith("https://www.gbif.org/") else "NC State Extension",
              item["source"])

    def add(key, value, reference=source, evidence="botanical"):
        publisher, url = reference
        rows[key] = {"value": value, "source": {"label": publisher, "url": url},
                     "evidence": tr(f"botany.evidence.{evidence}")}

    for key, fact in SPECIES.get(item["name"].lower(), {}).items():
        add(key, tr(fact.message), SOURCES[fact.source], fact.evidence)
    add("scientific_name", item.get("scientific", item["name"]))
    if item["family"]:
        add("family", item["family"])
    if gbif_key:
        if item["aliases"]:
            add("synonyms", " · ".join(item["aliases"]))
        if item["lineage"]:
            add("lineage", " › ".join(item["lineage"]))
        if item.get("countries"):
            add("observations", " · ".join(item["countries"]), ("GBIF", f"https://www.gbif.org/occurrence/search?taxon_key={gbif_key}"))
        if item.get("labels"):
            add("common_name", common_name(item, locale))
    label = common_name(item, locale)
    if label != item["name"] and ("common_name" not in rows or label != rows["common_name"]["value"]):
        rows["common_name"] = {"value": label, "source": None, "evidence": tr("library.name_index")}
    if item.get("light"):
        add("light", tr("library." + item["light"]))
        add("drainage", tr("library.drainage_value"))
    if item.get("food"):
        add("edible", tr("library.food_documented"))
        add("plant_parts", tr("library.part_" + item["food"]))
    for key, fact in item.get("facts", {}).items():
        add(key, tr("library." + fact["message"]), (fact["publisher"], fact["url"]), fact["evidence"])
    groups = {**GROUPS, "garden": (*GROUPS["garden"], "drainage"),
              "risks": (*GROUPS["risks"], "contraindications")}
    if gbif_key:
        groups["taxonomy"] += ("lineage", "synonyms", "observations")
    extras = {"drainage", "contraindications", "lineage", "synonyms", "observations"}
    field_label = lambda field: tr(("library." if field in extras else "botany.field.") + field)
    return {
        "id": item["id"], "kind": "taxonomy" if gbif_key else "reviewed", "license": backbone.LICENSE if gbif_key else None,
        "favorite": item["id"] in favorite_ids(owner), "photo": item.get("photo"),
        "notices": [tr("library.basic" if gbif_key else "library.verified"), *(tr(f"botany.notice.{kind}") for kind in ("identity", "risk", "emergency"))],
        "groups": [
            {"key": group, "title": tr(f"botany.group.{group}"), "items": [
                {"key": field, "label": field_label(field), **rows.get(field, {
                    "value": None, "evidence": tr("botany.evidence.unknown"), "source": None,
                })} for field in fields
            ]} for group, fields in groups.items()
        ],
    }


def category_label(tr, key):
    return tr(("botany.field." if key in FILTERS or key in {"skin", "hair"} else "library.") + key)
