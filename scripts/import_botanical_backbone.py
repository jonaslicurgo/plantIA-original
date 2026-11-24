"""Stream the licensed GBIF Backbone into a replaceable read-only SQLite catalog."""

import argparse
import csv
import gzip
import io
import json
import resource
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BACKBONE = "https://hosted-datasets.gbif.org/datasets/backbone/current/simple.txt.gz"
REVIEWED = Path(__file__).parents[1] / "plantia/data/botanical_catalog.json"
NULL = r"\N"


def normalized_name(value):
    return " ".join(value.casefold().replace("×", "").split())


def build(stream, target, minimum, etag=""):
    reviewed = json.loads(REVIEWED.read_text(encoding="utf-8"))
    names = {normalized_name(name): item["id"] for item in reviewed
             for name in (item["name"], *item.get("aliases", []))}
    with sqlite3.connect(target) as db:
        db.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA cache_size=-12000;
            CREATE TABLE taxa (id INTEGER PRIMARY KEY, name TEXT NOT NULL, scientific TEXT NOT NULL,
                parent INTEGER, family INTEGER, rank TEXT NOT NULL, reviewed TEXT);
            CREATE TABLE names (taxon INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL DEFAULT '',
                UNIQUE(taxon,name,kind,language));
            CREATE VIRTUAL TABLE names_search USING fts5(name, content='names', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2', prefix='2 3');
            CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        taxa, aliases = [], []
        def flush():
            db.executemany("INSERT OR IGNORE INTO taxa VALUES (?,?,?,?,?,?,?)", taxa)
            db.executemany("INSERT OR IGNORE INTO names(taxon,name,kind) VALUES (?,?,?)", aliases)
            taxa.clear()
            aliases.clear()

        for row in csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) != 30 or row[10] != "6":
                continue
            key, parent = row[:2]
            status, rank = row[4:6]
            name, canonical = row[18:20]
            if canonical == NULL or not key.isdecimal():
                continue
            if status == "ACCEPTED":
                taxa.append((int(key), canonical, name, int(parent) if parent.isdecimal() else None,
                             int(row[14]) if row[14].isdecimal() else None, rank, names.get(normalized_name(canonical))))
                if rank == "SPECIES":
                    aliases.append((int(key), canonical, "scientific"))
            elif rank == "SPECIES" and parent.isdecimal() and status.endswith("SYNONYM"):
                aliases.append((int(parent), canonical, "synonym"))
            if len(taxa) + len(aliases) >= 4000:
                flush()
        flush()
        db.execute("DELETE FROM names WHERE taxon NOT IN (SELECT id FROM taxa WHERE rank='SPECIES')")
        db.execute("CREATE INDEX species_listing ON taxa(rank,reviewed,id)")
        db.execute("INSERT INTO names_search(names_search) VALUES ('rebuild')")
        count = db.execute("SELECT count(*) FROM taxa WHERE rank='SPECIES' AND reviewed IS NULL").fetchone()[0]
        if count < minimum or db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError(f"Import rejected: {count} accepted non-curated species")
        db.executemany('INSERT INTO metadata VALUES (?,?)', [('species', str(count)), ('etag', etag),
            ('source', BACKBONE), ('license', 'https://creativecommons.org/licenses/by/4.0/')])
        aliases_count = db.execute("SELECT count(*) FROM names WHERE kind='synonym'").fetchone()[0]
        return count, aliases_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="Optional official simple.txt.gz snapshot")
    parser.add_argument("--min-species", type=int, default=100_000)
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.parent.is_dir() or shutil.disk_usage(target.parent).free < 400_000_000:
        parser.error("Reserve at least 400 MB free alongside the destination")
    tmp = tempfile.NamedTemporaryFile(prefix=".botanical-", suffix=".sqlite", dir=target.parent, delete=False)
    tmp.close()
    stage = Path(tmp.name)
    try:
        headers = {"User-Agent": "PLANET-IA botanical importer/1.0"}
        if target.is_file() and not args.input:
            with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as current:
                row = current.execute("SELECT value FROM metadata WHERE key='etag'").fetchone()
                if row and row[0]:
                    headers["If-None-Match"] = row[0]
        try:
            source = args.input.open("rb") if args.input else urlopen(Request(
                BACKBONE, headers=headers), timeout=45)
        except HTTPError as error:
            if error.code == 304:
                print("GBIF snapshot unchanged")
                return
            raise
        with source, gzip.GzipFile(fileobj=source) as compressed, io.TextIOWrapper(compressed, encoding="utf-8") as stream:
            etag = "" if args.input else source.headers.get("ETag", "")
            if headers.get("If-None-Match") and etag == headers["If-None-Match"]:
                print("GBIF snapshot unchanged")
                return
            count, aliases = build(stream, stage, args.min_species, etag)
        os.replace(stage, target)
        print(json.dumps({"species": count, "synonyms": aliases, "bytes": target.stat().st_size,
                          "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))

    finally:
        stage.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
