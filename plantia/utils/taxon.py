"""Shared Unicode search normalization and binomial validation."""

import re
import unicodedata

TAXON_NAME = re.compile(r"[A-Za-z][A-Za-z-]{1,48}\s+[A-Za-z][A-Za-z-]{1,48}", re.ASCII)


def normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", " ".join((value or "").casefold().split()))
    return "".join(char for char in text if not unicodedata.combining(char))


def species_name(value: str) -> str | None:
    name = " ".join(value.split())
    return normalize(name) if TAXON_NAME.fullmatch(name) else None
