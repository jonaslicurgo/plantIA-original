"""Encyclopedia records corroborated by public botanical references."""

from dataclasses import dataclass
import json
from http.client import HTTPException
from threading import Lock
from time import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text

from plantia.database import get_engine
from plantia.utils.taxon import species_name

GROUPS = {
    "taxonomy": ("common_name", "scientific_name", "family", "origin", "traits", "habitat"),
    "uses": ("ornamental", "medicinal", "edible", "panc", "aromatic", "seasoning", "plant_parts"),
    "risks": ("toxic", "human_toxicity", "animal_toxicity", "toxic_parts", "exposure"),
    "cosmetic": ("cosmetics", "skin", "hair", "fragrance", "essential_oils"),
    "garden": ("landscaping", "indoors_outdoors", "balcony", "light", "pollinators", "repellent"),
    "ecology": ("invasive", "conservation"),
}


@dataclass(frozen=True)
class Fact:
    message: str
    source: str
    evidence: str = "botanical"


SOURCES = {
    "lavender_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/lavandula-angustifolia/"),
    "lavender_nih": ("NIH · NCCIH", "https://www.nccih.nih.gov/health/lavender"),
    "pothos_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/epipremnum-aureum/"),
    "pothos_aspca": ("ASPCA Poison Control", "https://www.aspca.org/pet-care/aspca-poison-control/toxic-and-non-toxic-plants/golden-pothos"),
    "mentha_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/mentha-spicata/"),
    "dionaea_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/dionaea-muscipula/"),
    "aloe_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/aloe-vera/"),
    "aloe_nih": ("NIH · NCCIH", "https://www.nccih.nih.gov/health/aloe-vera"),
    "purslane_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/portulaca-oleracea/"),
    "purslane_embrapa": ("Embrapa · Plantas Alimentícias Não Convencionais & Saúde", "https://www.infoteca.cnptia.embrapa.br/infoteca/handle/doc/1132694"),
    "lantana_nc": ("NC State Extension", "https://plants.ces.ncsu.edu/plants/lantana-camara/"),
    "dionaea_fws": ("U.S. Fish & Wildlife Service", "https://www.fws.gov/species/venus-fly-trap-dionaea-muscipula"),
}

# Each assertion is attached to the page that supports it. Missing fields stay unknown.
SPECIES = {
    "lavandula angustifolia": {
        "common_name": Fact("English lavender", "lavender_nc"),
        "origin": Fact("Native to the Mediterranean region.", "lavender_nc"),
        "traits": Fact("An evergreen shrub with narrow leaves and fragrant flower spikes.", "lavender_nc"),
        "family": Fact("Lamiaceae", "lavender_nc"),
        "ornamental": Fact("Cultivated for its fragrant flowers and foliage.", "lavender_nc"),
        "medicinal": Fact("Lavender has a history of medicinal use. NCCIH reports uncertainty about benefits for many proposed uses.", "lavender_nih", "traditional"),
        "aromatic": Fact("The foliage and flowers are fragrant.", "lavender_nc"),
        "fragrance": Fact("NCCIH describes lavender as an ingredient in bath products and perfumes.", "lavender_nih"),
        "cosmetics": Fact("Lavender is used as a fragrance ingredient in bath products. This does not imply benefits or suitability for skin.", "lavender_nih"),
        "essential_oils": Fact("Lavender essential oil is studied in aromatherapy. Evidence and safety depend on the form and use.", "lavender_nih", "limited"),
        "skin": Fact("NCCIH notes that topical lavender products may cause allergic skin reactions.", "lavender_nih", "limited"),
        "landscaping": Fact("Grown in herb gardens, borders and containers.", "lavender_nc"),
        "light": Fact("Prefers full sun and well-drained soil.", "lavender_nc"),
        "pollinators": Fact("The flowers attract butterflies and other pollinators.", "lavender_nc"),
    },
    "epipremnum aureum": {
        "common_name": Fact("Golden pothos", "pothos_nc"),
        "family": Fact("Araceae", "pothos_nc"),
        "traits": Fact("A climbing or trailing vine with glossy, often variegated leaves.", "pothos_nc"),
        "ornamental": Fact("Commonly grown as an indoor ornamental vine.", "pothos_nc"),
        "toxic": Fact("Contains insoluble calcium oxalate crystals.", "pothos_nc"),
        "human_toxicity": Fact("Exposure can irritate the mouth. Treat suspected ingestion by a child or adult as a reason to seek poison-control guidance.", "pothos_nc"),
        "animal_toxicity": Fact("ASPCA lists golden pothos as toxic to dogs and cats. Oral irritation and difficulty swallowing are among the reported signs. Other animals are not covered by this record.", "pothos_aspca"),
        "toxic_parts": Fact("Leaves and stems are listed among the parts of concern.", "pothos_nc"),
        "exposure": Fact("Chewing the plant can cause oral pain. Sap can irritate the skin.", "pothos_nc"),
        "indoors_outdoors": Fact("Often kept indoors as a trailing or climbing houseplant.", "pothos_nc"),
        "balcony": Fact("Can be grown indoors in hanging containers. Keep it away from children and pets.", "pothos_nc"),
        "light": Fact("Grows in bright indirect light and tolerates lower light.", "pothos_nc"),
    },
    "aloe vera": {
        "common_name": Fact("Aloe vera", "aloe_nc"),
        "family": Fact("Asphodelaceae", "aloe_nc"),
        "origin": Fact("Native to the Arabian Peninsula. It has spread to many other regions.", "aloe_nc"),
        "traits": Fact("An evergreen succulent with thick leaves.", "aloe_nc"),
        "ornamental": Fact("Often grown indoors as a houseplant.", "aloe_nc"),
        "medicinal": Fact("Aloe has a history of medicinal use. Evidence varies by preparation and intended use.", "aloe_nih", "traditional"),
        "hair": Fact("NCCIH mentions traditional uses involving hair. The cited source does not establish clinical benefit for hair.", "aloe_nih", "traditional"),
        "skin": Fact("NCCIH reviews research on topical aloe and reports occasional burning, itching, rash or eczema.", "aloe_nih", "limited"),
        "exposure": Fact("NCCIH describes adverse effects and possible medicine interactions from oral use, particularly with aloe latex. The gel and latex are distinct preparations.", "aloe_nih", "limited"),
        "indoors_outdoors": Fact("Often grown indoors and can grow outdoors in warm climates.", "aloe_nc"),
        "light": Fact("Grows in full sun to partial shade.", "aloe_nc"),
        "invasive": Fact("Reported as invasive in some areas. Check the applicable local species list.", "aloe_nc"),
    },
    "lantana camara": {
        "common_name": Fact("Common lantana", "lantana_nc"),
        "family": Fact("Verbenaceae", "lantana_nc"),
        "origin": Fact("Native from Mexico to tropical America.", "lantana_nc"),
        "ornamental": Fact("Grown as an ornamental for its clusters of flowers.", "lantana_nc"),
        "human_toxicity": Fact("The source reports vomiting and diarrhea after ingestion. Seek poison-control guidance for exposure in adults or children.", "lantana_nc"),
        "toxic_parts": Fact("The source lists flowers, fruits, leaves and sap as parts of concern.", "lantana_nc"),
        "toxic": Fact("The source lists toxic triterpenoids.", "lantana_nc"),
        "pollinators": Fact("The flowers attract butterflies.", "lantana_nc"),
    },
    "mentha spicata": {
        "common_name": Fact("Spearmint", "mentha_nc"),
        "family": Fact("Lamiaceae", "mentha_nc"),
        "traits": Fact("A fragrant perennial herb that spreads readily.", "mentha_nc"),
        "aromatic": Fact("The leaves have a characteristic mint fragrance.", "mentha_nc"),
        "seasoning": Fact("The source documents culinary use of cultivated spearmint. This record is not a consumption recommendation.", "mentha_nc"),
        "edible": Fact("Culinary use is documented for the cultivated species. A photo does not establish the identity or safety of a specimen.", "mentha_nc"),
        "plant_parts": Fact("Leaves are the part associated with documented culinary use.", "mentha_nc"),
        "light": Fact("Grows in full sun to partial shade.", "mentha_nc"),
    },
    "portulaca oleracea": {
        "common_name": Fact("Common purslane", "purslane_nc"),
        "family": Fact("Portulacaceae", "purslane_nc"),
        "traits": Fact("An annual succulent with fleshy leaves, low reddish stems and small yellow flowers.", "purslane_nc"),
        "origin": Fact("Widely distributed worldwide. The source notes uncertainty about its native status in North America.", "purslane_nc"),
        "panc": Fact("Embrapa documents common purslane as an unconventional food plant in Brazil. This classification does not establish the identity or safety of a specimen.", "purslane_embrapa"),
        "edible": Fact("Embrapa records food use in Brazil. This is a record of use and not a recommendation to eat a plant identified by photo.", "purslane_embrapa"),
        "light": Fact("The source describes full sun and well-drained soil.", "purslane_nc"),
    },
    "dionaea muscipula": {
        "common_name": Fact("Venus flytrap", "dionaea_nc"),
        "family": Fact("Droseraceae", "dionaea_nc"),
        "origin": Fact("Native to a small area of the coastal plain of North and South Carolina.", "dionaea_fws"),
        "habitat": Fact("Occurs in wet, open habitats on the Carolina coastal plain.", "dionaea_fws"),
        "traits": Fact("A carnivorous plant with modified leaves that close around small prey.", "dionaea_nc"),
        "ornamental": Fact("Cultivated as a carnivorous ornamental plant.", "dionaea_nc"),
        "conservation": Fact("A narrowly distributed species with conservation concerns. The source describes threats including habitat loss and illegal collection.", "dionaea_fws"),
    },
}

FILTERS = ("ornamental", "medicinal", "edible", "panc", "toxic", "aromatic", "cosmetics",
           "essential_oils", "seasoning", "landscaping", "indoors_outdoors", "light",
           "pollinators", "repellent", "invasive", "conservation")

# Only normalized taxon names and vetted public GBIF fields enter this cache.
_CACHE_LOCKS = tuple(Lock() for _ in range(32))


def _fetch_taxon(name: str) -> dict:
    query = urlencode({"name": name, "kingdom": "Plantae", "strict": "true"})
    request = Request(f"https://api.gbif.org/v1/species/match?{query}", headers={"User-Agent": "PLANET-IA/1"})
    with urlopen(request, timeout=4) as response:
        match = json.loads(response.read(64 * 1024))
    if not isinstance(match, dict):
        raise ValueError("Unexpected GBIF response")
    key = match.get("usageKey")
    if (match.get("matchType") != "EXACT" or match.get("rank") != "SPECIES"
            or match.get("kingdom") != "Plantae" or match.get("status") != "ACCEPTED"
            or species_name(str(match.get("canonicalName", ""))) != name
            or not isinstance(key, int) or key <= 0):
        return {}
    return {"key": key, "scientific_name": str(match["canonicalName"]), "family": str(match.get("family") or "")[:100]}


def get_taxon(name: str) -> dict:
    with _CACHE_LOCKS[hash(name) % len(_CACHE_LOCKS)]:
        engine = get_engine()
        now = int(time())
        with engine.connect() as db:
            row = db.execute(text("SELECT payload FROM botany_cache WHERE taxon=:taxon AND expires>:now"),
                             {"taxon": name, "now": now}).scalar()
        if row is not None:
            return json.loads(row)
        try:
            facts = _fetch_taxon(name)
        except (URLError, OSError, ValueError, HTTPException):
            return {}
        with engine.begin() as db:
            db.execute(text("DELETE FROM botany_cache WHERE expires<=:now"), {"now": now})
            db.execute(text("""INSERT INTO botany_cache(taxon,payload,expires) VALUES (:taxon,:payload,:expires)
                ON CONFLICT(taxon) DO UPDATE SET payload=excluded.payload, expires=excluded.expires"""),
                {"taxon": name, "payload": json.dumps(facts), "expires": now + (7 * 86400 if facts else 6 * 3600)})
        return facts


def profile(plant, translate):
    name = species_name(plant.nombre_cientifico) if plant.confianza in {"alto", "medio"} else None
    curated = SPECIES.get(name, {})
    taxon = get_taxon(name) if name else {}
    rows = {}
    for field, fact in curated.items():
        publisher, url = SOURCES[fact.source]
        rows[field] = {"value": translate(fact.message), "evidence": translate(f"botany.evidence.{fact.evidence}"),
                       "source": {"label": publisher, "url": url}}
    if curated:
        reference = curated["family"].source
        publisher, url = SOURCES[reference]
        rows["scientific_name"] = {"value": plant.nombre_cientifico.strip(), "evidence": translate("botany.evidence.botanical"),
                                   "source": {"label": publisher, "url": url}}
    for field in ("scientific_name", "family"):
        if taxon.get(field):
            rows[field] = {"value": taxon[field], "evidence": translate("botany.evidence.botanical"),
                           "source": {"label": "GBIF", "url": f"https://www.gbif.org/species/{taxon['key']}"}}
    for field, value in (("common_name", plant.nombre_comun), ("scientific_name", plant.nombre_cientifico if name else None)):
        if value and field not in rows:
            rows[field] = {"value": value, "evidence": translate("botany.evidence.suggested"), "source": None}

    notices = [translate(f"botany.notice.{kind}") for kind in ("identity", "risk", "emergency")]
    if not (taxon or curated):
        notices.append(translate("botany.unverified"))
    return {
        "id": plant.id,
        "favorite": plant.encyclopedia_favorite,
        "matched_taxon": bool(taxon or curated),
        "notices": notices,
        "groups": [
            {"key": group, "title": translate(f"botany.group.{group}"), "items": [
                {"key": field, "label": translate(f"botany.field.{field}"), **(
                    rows.get(field) or {"value": None, "evidence": translate("botany.evidence.unknown"), "source": None}
                )}
                for field in fields
            ]}
            for group, fields in GROUPS.items()
        ],
    }
