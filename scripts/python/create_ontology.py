import argparse
import csv
import json
import labelbox as lb
import logging
import os
import requests
import sys

from dotenv import load_dotenv
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIGURATION — edit these for each project
# ---------------------------------------------------------------------------

# Input CSV path (relative to project root)
INPUT_CSV = "projects/2024_bci/BCNM_SPECIES_BOTANISTS_LIST_2026-04-30.csv"

# CSV format
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"

# CSV column names
COL_BINOMIAL = "current_binomial"
COL_CODE1 = "sp6"   # optional extra code appended to label (set to None to omit)
COL_CODE2 = "sp4"   # optional extra code appended to label (set to None to omit)
COL_GENUS = "wcvp_matched_name"
COL_FAMILY = "wcvp_accepted_family"
COL_GBIF_ID = "wcvp_matched_name_gbif_id"

# Label format: binomial + non-empty codes joined by this separator
LABEL_SEPARATOR = "-"

# Labelbox ontology structure
ONTOLOGY_NAME = "BCNM 2026 - Planta"
BBOX_TOOL_NAME = "Planta"
TAXON_CLASS_NAME = "Taxón"
ORGAN_CLASS_NAME = "Órgano"

# Órgano checklist options: list of (value, label) tuples
ORGAN_OPTIONS = [
    ("flor", "Flor"),
    ("fruto", "Fruto"),
]

# Output folder for Labelbox list CSV (relative to project root)
OUTPUT_DIR = "projects/2024_bci"

# GBIF cache file (relative to project root)
GBIF_CACHE_FILE = "projects/2024_bci/gbif_cache.json"

# GBIF API
GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_MAX_RETRIES = 3
GBIF_PHYLUM = "Tracheophyta"

# ---------------------------------------------------------------------------
# END CONFIGURATION
# ---------------------------------------------------------------------------

project_root = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=project_root / ".env")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
stdout_handler.addFilter(lambda record: record.levelno == logging.INFO)
stdout_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

logger.handlers = []
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def resolve_gbif(name: str, rank: str, cache: dict) -> int | None:
    key = f"{name}|{rank}"
    if key in cache:
        return cache[key]

    params = {"name": name, "rank": rank}
    if GBIF_PHYLUM:
        params["phylum"] = GBIF_PHYLUM

    for attempt in range(GBIF_MAX_RETRIES):
        try:
            r = requests.get(GBIF_MATCH_URL, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("matchType") == "EXACT":
                usage_key = data.get("usageKey")
                cache[key] = usage_key
                return usage_key
            else:
                cache[key] = None
                return None
        except Exception as e:
            if attempt == GBIF_MAX_RETRIES - 1:
                logger.warning(f"GBIF lookup failed for {name} ({rank}) after {GBIF_MAX_RETRIES} attempts: {e}")
    cache[key] = None
    return None


def build_species_label(row: dict) -> str:
    parts = [row[COL_BINOMIAL]]
    for col in (COL_CODE1, COL_CODE2):
        if col is not None:
            code = row.get(col, "").strip()
            if code:
                parts.append(code)
    return LABEL_SEPARATOR.join(parts)


def load_species_rows() -> list[dict]:
    csv_path = project_root / INPUT_CSV
    rows = []
    with open(csv_path, encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        for row in reader:
            rows.append(row)
    return rows


def extract_genera(rows: list[dict]) -> list[str]:
    seen = set()
    genera = []
    for row in rows:
        col_genus = row.get(COL_GENUS, "").strip()
        if not col_genus:
            continue
        genus = col_genus.split()[0]
        if genus not in seen:
            seen.add(genus)
            genera.append(genus)
    return sorted(genera)


def extract_families(rows: list[dict]) -> list[str]:
    seen = set()
    families = []
    for row in rows:
        col_family = row.get(COL_FAMILY, "").strip()
        if col_family and col_family not in seen:
            seen.add(col_family)
            families.append(col_family)
    return sorted(families)


def prompt_manual_gbif_id(name: str, rank: str, suggestion: str | None, cache: dict) -> int | None:
    hint = f" (e.g. search GBIF for '{suggestion}')" if suggestion else ""
    print(f"\n  No exact GBIF match for {rank.lower()} '{name}'{hint}.")
    while True:
        try:
            raw = input(f"  Enter GBIF ID for '{name}': ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.isdigit():
            gbif_id = int(raw)
            cache[f"{name}|{rank}"] = gbif_id
            return gbif_id
        print("  Invalid input — please enter a numeric ID.")


def build_taxon_options(rows: list[dict], cache: dict) -> list[dict]:
    options = []
    seen_ids = set()

    # Species
    for row in rows:
        gbif_id_raw = row.get(COL_GBIF_ID, "").strip()
        if not gbif_id_raw:
            logger.warning(f"Missing {COL_GBIF_ID} for row: {row.get(COL_BINOMIAL, '?')} — skipping")
            continue
        try:
            gbif_id = int(gbif_id_raw)
        except ValueError:
            logger.warning(f"Non-integer {COL_GBIF_ID} '{gbif_id_raw}' for {row.get(COL_BINOMIAL, '?')} — skipping")
            continue
        if gbif_id in seen_ids:
            continue
        seen_ids.add(gbif_id)
        options.append({"type": "species", "label": build_species_label(row), "value": str(gbif_id)})

    # Genera
    for genus in extract_genera(rows):
        gbif_id = resolve_gbif(genus, "GENUS", cache)
        if gbif_id is None:
            example = next(
                (r[COL_BINOMIAL] for r in rows if r.get(COL_GENUS, "").split()[0:1] == [genus]),
                None,
            )
            gbif_id = prompt_manual_gbif_id(genus, "GENUS", example, cache)
        if gbif_id is None or gbif_id in seen_ids:
            continue
        seen_ids.add(gbif_id)
        options.append({"type": "genus", "label": genus, "value": str(gbif_id)})

    # Families
    for family in extract_families(rows):
        gbif_id = resolve_gbif(family, "FAMILY", cache)
        if gbif_id is None:
            example = next(
                (r[COL_BINOMIAL] for r in rows if r.get(COL_FAMILY, "").strip() == family),
                None,
            )
            gbif_id = prompt_manual_gbif_id(family, "FAMILY", example, cache)
        if gbif_id is None or gbif_id in seen_ids:
            continue
        seen_ids.add(gbif_id)
        options.append({"type": "family", "label": family, "value": str(gbif_id)})

    return options


def save_list(options: list[dict]) -> None:
    output_path = project_root / OUTPUT_DIR
    output_path.mkdir(parents=True, exist_ok=True)
    list_file = output_path / "labelbox_list.csv"
    with open(list_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["type", "label", "value"])
        writer.writeheader()
        writer.writerows(options)
    logger.info(f"List saved to {list_file} ({len(options)} rows)")


def build_ontology(options: list[dict]) -> lb.OntologyBuilder:
    taxon_options = [lb.Option(value=o["value"], label=o["label"]) for o in options]
    organ_options = [lb.Option(value=v, label=l) for v, l in ORGAN_OPTIONS]

    tool = lb.Tool(
        tool=lb.Tool.Type.BBOX,
        name=BBOX_TOOL_NAME,
        classifications=[
            lb.Classification(
                class_type=lb.Classification.Type.RADIO,
                name=TAXON_CLASS_NAME,
                options=taxon_options,
            ),
            lb.Classification(
                class_type=lb.Classification.Type.CHECKLIST,
                name=ORGAN_CLASS_NAME,
                options=organ_options,
            ),
        ],
    )

    return lb.OntologyBuilder(tools=[tool])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Labelbox ontology from a species CSV.")
    parser.parse_args()

    cache_path = project_root / GBIF_CACHE_FILE
    cache = load_cache(cache_path)

    logger.info(f"Loading species list from {INPUT_CSV}")
    rows = load_species_rows()
    logger.info(f"{len(rows)} rows loaded")

    logger.info("Resolving GBIF IDs for species, genera, and families…")
    options = build_taxon_options(rows, cache)
    save_cache(cache, cache_path)

    species_count = sum(1 for o in options if o["type"] == "species")
    genus_count = sum(1 for o in options if o["type"] == "genus")
    family_count = sum(1 for o in options if o["type"] == "family")
    logger.info(f"Taxón options: {species_count} species, {genus_count} genera, {family_count} families ({len(options)} total)")

    save_list(options)

    try:
        answer = input(f"\nReview the list above and confirm creation of '{ONTOLOGY_NAME}' in Labelbox. Type 'yes' to proceed: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        logger.info("Aborted.")
        return

    if answer != "yes":
        logger.info("Aborted.")
        return

    LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")
    if not LABELBOX_API_KEY:
        logger.error("LABELBOX_API_KEY environment variable is not set")
        sys.exit(1)

    client = lb.Client(api_key=LABELBOX_API_KEY)
    ontology_builder = build_ontology(options)

    logger.info(f"Creating ontology '{ONTOLOGY_NAME}' in Labelbox…")
    ontology = client.create_ontology(
        name=ONTOLOGY_NAME,
        normalized=ontology_builder.asdict(),
        media_type=lb.MediaType.Image,
    )
    logger.info(f"Ontology created: {ontology.uid}")


if __name__ == "__main__":
    main()
