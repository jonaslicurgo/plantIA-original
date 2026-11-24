"""Warm evidence for the priority species, without using Gemini."""
from main import app  # Initialize the additive tables on the configured volume.
from plantia.i18n import catalog
from plantia.services.botanical_enrichment import PRIORITIES, facts


def main():
    translate = catalog("pt-BR").__getitem__
    for name, family in PRIORITIES.items():
        evidence = facts({"name": name, "family": family}, "pt-BR", translate)
        print(f"{name}: {len(evidence)} sourced entries")


if __name__ == "__main__":
    main()
