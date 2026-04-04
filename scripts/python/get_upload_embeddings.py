"""
Get Pl@ntNet embeddings for Labelbox datasets matching keyword(s) and upload them.

Searches Labelbox for all datasets whose name contains any of the given keywords,
exports their data rows to get image URLs (no local file download — everything
is in-memory), requests embeddings from the Pl@ntNet /v2/embeddings endpoint,
caches results per data row ID, then uploads vectors to a custom Labelbox embedding.

Usage:
  # Test with one dataset, one image
  python get_upload_embeddings.py --keywords bci plots --test-one

  # Test with first N matching datasets
  python get_upload_embeddings.py --keywords bci plots --test-datasets 2

  # Process all matching datasets
  python get_upload_embeddings.py --keywords bci plots

  # Custom delay between API calls
  python get_upload_embeddings.py --keywords bci plots --delay 1.0
"""

import argparse
import io
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import labelbox as lb
import requests
import yaml
from dotenv import load_dotenv
from PIL import Image

# ── Configuration ──────────────────────────────────────────────────────────────
KEYWORDS = ["<keyword_1>", "<keyword_2>"]   # dataset name substrings to match (case-insensitive)
KEYWORDS = ["2024_bci", "2025_tiputini", "2024_panama"]   # dataset name substrings to match (case-insensitive)

EMBEDDING_NAME = "<embedding_name>"         # custom Labelbox embedding name, e.g. "PlantNet-v7.4-1280px"
EMBEDDING_NAME = "PlantNet-v7.4-1280px"         # custom Labelbox embedding name, e.g. "PlantNet-v7.4-1280px"
EMBEDDING_DIMS = 768                        # must match the Pl@ntNet model output dimensions

PLANTNET_API_URL = "https://my-api.plantnet.org/v2/embeddings"

OUTPUT_DIR   = Path("output/embeddings")    # where to save cache and outputs
CROP_SIZE    = 1280                         # center-crop size before sending to Pl@ntNet
JPEG_QUALITY = 90
BATCH_SIZE   = 1000                         # vectors per Labelbox upload batch
MAX_RETRIES  = 3
DEFAULT_DELAY = 0.5                         # seconds between Pl@ntNet API calls
IMAGE_DOWNLOAD_TIMEOUT = 30
API_TIMEOUT  = 60
EXPORT_TIMEOUT_SEC = 300

# ── Exceptions ─────────────────────────────────────────────────────────────────

class QuotaExceededError(Exception):
    pass

# ── Pl@ntNet helpers ───────────────────────────────────────────────────────────

def download_image_to_memory(url: str) -> bytes:
    """Download image URL into memory (no local file written)."""
    resp = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def center_crop_to_jpeg(image_bytes: bytes) -> tuple:
    """Center-crop to CROP_SIZE x CROP_SIZE, return JPEG bytes and metadata dict."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    meta = {"original_width": w, "original_height": h, "crop_size": None}

    if w >= CROP_SIZE and h >= CROP_SIZE:
        left = (w - CROP_SIZE) // 2
        top  = (h - CROP_SIZE) // 2
        img  = img.crop((left, top, left + CROP_SIZE, top + CROP_SIZE))
        meta["crop_size"] = CROP_SIZE
    else:
        print(f"    WARNING: image is {w}x{h}, smaller than {CROP_SIZE}x{CROP_SIZE} — sending as-is")

    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue(), meta


def call_embeddings_api(jpeg_bytes: bytes, filename: str, api_key: str) -> dict:
    """POST cropped JPEG bytes to Pl@ntNet /v2/embeddings. Returns raw JSON."""
    files  = [("image", (filename, io.BytesIO(jpeg_bytes), "image/jpeg"))]
    params = {"api-key": api_key}
    resp   = requests.post(PLANTNET_API_URL, files=files, params=params, timeout=API_TIMEOUT)

    if resp.status_code == 429:
        raise QuotaExceededError(f"Pl@ntNet quota exceeded (HTTP 429): {resp.text}")
    resp.raise_for_status()
    return resp.json()


def extract_embedding(api_response: dict) -> tuple:
    """
    Extract (embedding_list, version_str) from an API response.
    Handles flat vectors and tile-style responses (mean-pooled + L2-normalised).
    """
    embedding = None
    for key in ("embedding", "embeddings", "vector"):
        if key not in api_response:
            continue
        val = api_response[key]
        if not (isinstance(val, list) and val):
            continue
        if isinstance(val[0], (int, float)):
            embedding = val
        elif isinstance(val[0], dict) and "embeddings" in val[0]:
            dims     = len(val[0]["embeddings"])
            mean_vec = [0.0] * dims
            for tile in val:
                for j, v in enumerate(tile["embeddings"]):
                    mean_vec[j] += v
            mean_vec = [v / len(val) for v in mean_vec]
            norm = math.sqrt(sum(v * v for v in mean_vec))
            if norm > 0:
                mean_vec = [v / norm for v in mean_vec]
            embedding = mean_vec
        break

    if embedding is None:
        raise ValueError(
            f"Could not find embedding in API response. Keys: {list(api_response.keys())}. "
            "Run with --test-one to inspect the full response."
        )

    version = None
    for key in ("version", "plantnet_version", "model_version", "model"):
        if key in api_response and isinstance(api_response[key], str):
            version = api_response[key]
            break

    return embedding, version


def verify_version_against_name(api_version: str | None, embedding_name: str):
    """
    If EMBEDDING_NAME contains a version tag like 'v7.4', confirm it matches
    the version string returned by the API (e.g. '2026-02-17 (7.4)').
    Exits immediately if they disagree.
    Does nothing if embedding_name has no recognisable version tag.
    """
    name_match = re.search(r"v(\d+\.\d+)", embedding_name)
    if not name_match:
        return  # name has no version tag — nothing to check

    name_ver = name_match.group(1)

    if not api_version:
        print(f"  WARNING: EMBEDDING_NAME suggests version {name_ver} "
              f"but the API returned no version string — cannot verify.")
        return

    api_match = re.search(r"\((\d+\.\d+)\)", api_version)
    if not api_match:
        print(f"  WARNING: Could not parse version from API response '{api_version}' — cannot verify.")
        return

    api_ver = api_match.group(1)
    if api_ver != name_ver:
        sys.exit(
            f"ERROR: Version mismatch — EMBEDDING_NAME implies v{name_ver} "
            f"but API returned '{api_version}' (v{api_ver}). "
            f"Update EMBEDDING_NAME or check your API endpoint."
        )
    print(f"  Version confirmed: EMBEDDING_NAME v{name_ver} matches API v{api_ver}")

# ── Cache helpers ──────────────────────────────────────────────────────────────

def get_version_slug(embedding_name: str) -> str:
    """Extract 'v7.4' from EMBEDDING_NAME, or 'unknown' if no version tag found."""
    m = re.search(r"(v\d+\.\d+)", embedding_name)
    return m.group(1) if m else "unknown"


def load_cache(cache_dir: Path, data_row_id: str, version_slug: str) -> dict | None:
    path = cache_dir / f"{data_row_id}_{version_slug}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_cache(cache_dir: Path, data_row_id: str, entry: dict, version_slug: str):
    path = cache_dir / f"{data_row_id}_{version_slug}.json"
    tmp  = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(entry, f)
    tmp.replace(path)


# def migrate_cache_to_versioned(cache_dir: Path):
#     """
#     One-time migration: rename old-style {id}.json files to {id}_{version_slug}.json
#     by reading the plantnet_version stored inside each file.
#     """
#     migrated = 0
#     for path in sorted(cache_dir.glob("*.json")):
#         if path.name.startswith("export_"):
#             continue
#         if re.search(r"_v\d+\.\d+\.json$", path.name):
#             continue  # already versioned
#         try:
#             with open(path) as f:
#                 entry = json.load(f)
#         except (json.JSONDecodeError, OSError):
#             continue
#         version = entry.get("plantnet_version")
#         m = re.search(r"\((\d+\.\d+)\)", version) if version else None
#         slug = f"v{m.group(1)}" if m else "unknown"
#         new_path = path.with_name(f"{path.stem}_{slug}.json")
#         path.rename(new_path)
#         migrated += 1
#     if migrated:
#         print(f"  Migrated {migrated} cache file(s) to versioned filenames")


def load_export_cache(cache_dir: Path, dataset_uid: str) -> list[dict] | None:
    path = cache_dir / f"export_{dataset_uid}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_export_cache(cache_dir: Path, dataset_uid: str, rows: list[dict]):
    path = cache_dir / f"export_{dataset_uid}.json"
    tmp  = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(rows, f)
    tmp.replace(path)

# ── Labelbox helpers ───────────────────────────────────────────────────────────

def find_datasets_by_keywords(client: lb.Client, keywords: list[str]) -> list:
    """Return all Labelbox datasets whose name contains any keyword (case-insensitive)."""
    lower_kws = [k.lower() for k in keywords]
    matched = [
        d for d in client.get_datasets()
        if any(kw in d.name.lower() for kw in lower_kws)
    ]
    return matched


def export_dataset_rows(dataset, verbose: bool = False) -> list[dict]:
    """
    Export a dataset and return a list of dicts with:
      data_row_id, global_key, image_url
    """
    if verbose:
        print(f"  Exporting data rows from '{dataset.name}'...")

    export_task = dataset.export(params={
        "attachments":      False,
        "metadata_fields":  False,
        "data_row_details": True,
        "embeddings":       False,
        "labels":           False,
    })
    export_task.wait_till_done(timeout_seconds=EXPORT_TIMEOUT_SEC)

    # Collect export errors
    try:
        errors = []
        export_task.get_buffered_stream(stream_type=lb.StreamType.ERRORS).start(
            stream_handler=lambda o: errors.append(o.json)
        )
        if errors:
            print(f"  WARNING: Export errors for '{dataset.name}': {errors}")
    except ValueError:
        pass

    rows = []
    def _collect(output):
        dr = output.json.get("data_row", {})
        if dr.get("id") and dr.get("row_data"):
            rows.append({
                "data_row_id": dr["id"],
                "global_key":  dr.get("global_key", ""),
                "image_url":   dr["row_data"],
            })

    export_task.get_buffered_stream(stream_type=lb.StreamType.RESULT).start(
        stream_handler=_collect
    )

    if verbose:
        print(f"  Found {len(rows)} data rows")
    return rows


def get_or_create_embedding(client: lb.Client, name: str, dims: int):
    """Return existing custom embedding or create a new one."""
    for emb in client.get_embeddings():
        if emb.name == name and emb.custom:
            if emb.dims != dims:
                sys.exit(f"ERROR: Existing embedding '{name}' has dims={emb.dims}, expected {dims}.")
            print(f"  Using existing embedding '{name}' (id={emb.id})")
            return emb
    print(f"  Creating new custom embedding '{name}' (dims={dims})...")
    emb = client.create_embedding(name=name, dims=dims)
    print(f"  Created embedding id={emb.id}")
    return emb


def upload_vectors(embedding, vectors: list[dict]):
    """
    Upload a list of {"id": data_row_id, "vector": [...]} dicts to Labelbox.
    Writes to a temporary in-memory NDJSON buffer.
    """
    ndjson_lines = "\n".join(json.dumps(v) for v in vectors)
    ndjson_bytes = ndjson_lines.encode()

    batch_count = 0
    def on_batch(resp):
        nonlocal batch_count
        batch_count += 1
        print(f"    Batch {batch_count} accepted")

    embedding.import_vectors_from_file(
        io.BytesIO(ndjson_bytes),
        callback=on_batch,
    )

# ── Main ───────────────────────────────────────────────────────────────────────

def process_dataset(dataset, cache_dir: Path, plantnet_api_key: str,
                    delay: float, verbose: bool, test_one: bool,
                    refresh_exports: bool = False,
                    version_slug: str = "unknown") -> list[dict]:
    """
    Fetch embeddings for all data rows in a dataset.
    Returns list of {"id": data_row_id, "vector": [...]} ready for Labelbox upload.
    """
    cached_rows = None if refresh_exports else load_export_cache(cache_dir, dataset.uid)
    if cached_rows is not None:
        print(f"  Export cache hit: {len(cached_rows)} rows (skipping Labelbox export)")
        rows = cached_rows
    else:
        rows = export_dataset_rows(dataset, verbose=True)
        save_export_cache(cache_dir, dataset.uid, rows)

    if test_one:
        rows = rows[:1]
        print(f"  TEST-ONE: processing 1 data row")

    cached   = sum(1 for r in rows if load_cache(cache_dir, r["data_row_id"], version_slug) is not None)
    print(f"  Total: {len(rows)}, cached: {cached}, remaining: {len(rows) - cached}")

    plantnet_version = None
    version_verified = False
    vectors = []

    for i, row in enumerate(rows, 1):
        dr_id = row["data_row_id"]
        url   = row["image_url"]

        # Cache hit
        cached_entry = load_cache(cache_dir, dr_id, version_slug)
        if cached_entry is not None:
            vectors.append({"id": dr_id, "vector": cached_entry["embedding"]})
            if plantnet_version is None:
                plantnet_version = cached_entry.get("plantnet_version")
            continue

        # Fetch + embed with retries
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if verbose:
                    print(f"    [{i}/{len(rows)}] Downloading {url[:80]}...")
                image_bytes = download_image_to_memory(url)

                jpeg_bytes, crop_meta = center_crop_to_jpeg(image_bytes)
                if verbose:
                    print(f"    Original: {crop_meta['original_width']}x{crop_meta['original_height']}, "
                          f"crop: {crop_meta['crop_size']}, JPEG: {len(jpeg_bytes)} bytes")

                api_response = call_embeddings_api(jpeg_bytes, dr_id, plantnet_api_key)
                if verbose:
                    resp_str = json.dumps(api_response, indent=2)
                    print(f"    API response:\n{resp_str[:2000]}{'...' if len(resp_str) > 2000 else ''}")

                embedding_vec, version = extract_embedding(api_response)

                # Verify version on first live API call
                if not version_verified:
                    verify_version_against_name(version, EMBEDDING_NAME)
                    version_verified = True

                if plantnet_version is None and version:
                    plantnet_version = version

                entry = {
                    "data_row_id":     dr_id,
                    "global_key":      row["global_key"],
                    "image_url":       url,
                    "embedding":       embedding_vec,
                    "original_width":  crop_meta["original_width"],
                    "original_height": crop_meta["original_height"],
                    "crop_size":       crop_meta["crop_size"],
                    "plantnet_version": version,
                }
                save_cache(cache_dir, dr_id, entry, version_slug)
                vectors.append({"id": dr_id, "vector": embedding_vec})
                success = True
                break

            except QuotaExceededError as e:
                print(f"\n  QUOTA EXCEEDED after {i-1} rows in '{dataset.name}'.")
                print(f"  {e}")
                print(f"  Re-run to resume from this dataset.")
                # Return what we have so far
                return vectors

            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = [1, 5, 10][attempt - 1]
                    print(f"  Attempt {attempt}/{MAX_RETRIES} failed for {dr_id}: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  FAILED after {MAX_RETRIES} attempts: {dr_id}: {e}")

        if success and not test_one and i < len(rows):
            time.sleep(delay)

        if not verbose and (i % 100 == 0 or i == len(rows)):
            print(f"  [{i}/{len(rows)}] vectors ready={len(vectors)}")

    return vectors


def main():
    parser = argparse.ArgumentParser(
        description="Get Pl@ntNet embeddings for Labelbox datasets matching keyword(s) and upload them."
    )
    parser.add_argument(
        "--keywords", nargs="+",
        help="One or more substrings to match against Labelbox dataset names (overrides config KEYWORDS)"
    )
    parser.add_argument(
        "--test-one", action="store_true",
        help="Process only the first matching dataset and only its first data row (verbose)"
    )
    parser.add_argument(
        "--test-datasets", type=int, metavar="N",
        help="Process only the first N matching datasets"
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Delay in seconds between Pl@ntNet API calls (default: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--refresh-exports", action="store_true",
        help="Ignore cached dataset exports and re-fetch from Labelbox"
    )
    args = parser.parse_args()

    load_dotenv()

    # Resolve keywords: CLI wins over config
    keywords = args.keywords if args.keywords else KEYWORDS
    if not keywords or keywords == ["<keyword_1>", "<keyword_2>"]:
        sys.exit("ERROR: Provide keywords via --keywords or set KEYWORDS in the config section.")

    # Validate config placeholders
    if "<" in PLANTNET_API_URL:
        sys.exit("ERROR: Set PLANTNET_API_URL in the config section.")
    if "<" in EMBEDDING_NAME:
        sys.exit("ERROR: Set EMBEDDING_NAME in the config section.")

    plantnet_api_key = os.environ.get("PLANTNET_API_KEY")
    if not plantnet_api_key:
        sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

    labelbox_api_key = os.environ.get("LABELBOX_API_KEY")
    if not labelbox_api_key:
        sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

    cache_dir = OUTPUT_DIR / "cache"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    version_slug = get_version_slug(EMBEDDING_NAME)
    print(f"Cache version slug: {version_slug}")
    # migrate_cache_to_versioned(cache_dir)

    # ── Find datasets ──────────────────────────────────────────────────────────
    client = lb.Client(api_key=labelbox_api_key)

    print(f"Searching Labelbox datasets for keywords: {keywords}")
    datasets = find_datasets_by_keywords(client, keywords)

    if not datasets:
        sys.exit(f"ERROR: No datasets found matching keywords {keywords}.")

    print(f"Found {len(datasets)} dataset(s):")
    for d in datasets:
        print(f"  • {d.name}  (id: {d.uid})")

    # Apply test-datasets limit
    if args.test_one:
        datasets = datasets[:1]
        print(f"\nTEST-ONE: using only first dataset: '{datasets[0].name}'")
    elif args.test_datasets:
        datasets = datasets[:args.test_datasets]
        print(f"\nTEST-DATASETS: using first {len(datasets)} dataset(s)")

    # ── Get or create Labelbox embedding ──────────────────────────────────────
    print(f"\nSetting up Labelbox embedding '{EMBEDDING_NAME}'...")
    lb_embedding = get_or_create_embedding(client, EMBEDDING_NAME, EMBEDDING_DIMS)

    # ── Process each dataset ───────────────────────────────────────────────────
    all_vectors = []
    run_summary = []

    for idx, dataset in enumerate(datasets, 1):
        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(datasets)}] Dataset: {dataset.name}")
        print(f"{'─' * 60}")

        vectors = process_dataset(
            dataset          = dataset,
            cache_dir        = cache_dir,
            plantnet_api_key = plantnet_api_key,
            delay            = args.delay,
            verbose          = args.test_one,
            test_one         = args.test_one,
            refresh_exports  = args.refresh_exports,
            version_slug     = version_slug,
        )

        print(f"  → {len(vectors)} vector(s) ready for upload")
        all_vectors.extend(vectors)

        run_summary.append({
            "dataset_name":   dataset.name,
            "dataset_id":     dataset.uid,
            "vectors_ready":  len(vectors),
        })

    # ── Upload to Labelbox ─────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Uploading {len(all_vectors)} vector(s) to Labelbox...")
    print(f"{'=' * 60}")

    if not all_vectors:
        sys.exit("No vectors to upload.")

    # Write NDJSON summary file alongside cache
    ndjson_path = OUTPUT_DIR / "embeddings_upload.ndjson"
    with open(ndjson_path, "w") as f:
        for v in all_vectors:
            f.write(json.dumps({"id": v["id"], "vector": v["vector"]}) + "\n")
    print(f"NDJSON written to {ndjson_path}")

    batch_count = 0
    def on_batch(resp):
        nonlocal batch_count
        batch_count += 1
        print(f"  Batch {batch_count} accepted")

    lb_embedding.import_vectors_from_file(str(ndjson_path), callback=on_batch)
    print("Upload submitted.")

    # Check vector count (async ingestion — retry a few times)
    print("\nWaiting for Labelbox to confirm ingestion...")
    confirmed = 0
    for attempt in range(6):
        time.sleep(5)
        confirmed = lb_embedding.get_imported_vector_count()
        print(f"  Attempt {attempt + 1}: {confirmed} vectors confirmed")
        if confirmed >= len(all_vectors):
            break

    # ── Final summary ──────────────────────────────────────────────────────────
    summary = {
        "keywords":          keywords,
        "datasets_processed": len(datasets),
        "total_vectors":     len(all_vectors),
        "confirmed_vectors": confirmed,
        "embedding_name":    lb_embedding.name,
        "embedding_id":      lb_embedding.id,
        "embedding_dims":    EMBEDDING_DIMS,
        "per_dataset":       run_summary,
        "test_one":          args.test_one,
        "test_datasets":     args.test_datasets,
        "timestamp":         datetime.now().isoformat(),
    }
    summary_path = OUTPUT_DIR / "embeddings_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Keywords:          {keywords}")
    print(f"  Datasets:          {len(datasets)}")
    print(f"  Vectors uploaded:  {len(all_vectors)}")
    print(f"  Vectors confirmed: {confirmed}")
    print(f"  Embedding:         {lb_embedding.name}  (id={lb_embedding.id})")
    print(f"  NDJSON:            {ndjson_path}")
    print(f"  Summary:           {summary_path}")
    print(f"{'=' * 60}")
    if confirmed < len(all_vectors):
        print("\nNOTE: Labelbox ingests vectors asynchronously — confirmed count may still be updating.")


if __name__ == "__main__":
    main()