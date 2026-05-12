"""
Get Pl@ntNet embeddings for a Labelbox project dataset and upload them.

Per-row cache files and the status summary are stored under
projects/<project>/cache/.  The script probes the PlantNet API with the
first dataset row on each run to discover the current model version and
builds the full embedding name from EMBEDDING_NAME_TEMPLATE.  Rows already
cached at that version are skipped, so the script resumes naturally after a
partial run or a quota stop.

When the daily quota (HTTP 429) is reached the script uploads whatever
vectors are ready, writes the status file, and exits with code 1 so the
caller knows to re-run tomorrow.

Usage:
  python get_upload_embeddings.py --project 2024_bci
  python get_upload_embeddings.py --project 2024_bci --test-one
  python get_upload_embeddings.py --project 2024_bci --delay 1.0
"""

import argparse
import io
import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import labelbox as lb
import requests
from dotenv import load_dotenv
from PIL import Image

# ── Logging ────────────────────────────────────────────────────────────────────

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

# ── Configuration ──────────────────────────────────────────────────────────────

EMBEDDING_NAME_TEMPLATE = "PlantNet-{version}-1280px"  # {version} filled from API (e.g. v7.4)
EMBEDDING_DIMS = 768

PLANTNET_API_URL = "https://my-api.plantnet.org/v2/embeddings"
CROP_SIZE = 1280
JPEG_QUALITY = 90
MAX_RETRIES = 3
DEFAULT_DELAY = 0.5
IMAGE_DOWNLOAD_TIMEOUT = 30
API_TIMEOUT = 60
EXPORT_TIMEOUT_SEC = 300


class QuotaExceededError(Exception):
    pass


# ── Image helpers ──────────────────────────────────────────────────────────────

def download_image_to_memory(url: str) -> bytes:
    resp = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def center_crop_to_jpeg(image_bytes: bytes) -> tuple:
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    meta = {"original_width": w, "original_height": h, "crop_size": None}

    if w >= CROP_SIZE and h >= CROP_SIZE:
        left = (w - CROP_SIZE) // 2
        top = (h - CROP_SIZE) // 2
        img = img.crop((left, top, left + CROP_SIZE, top + CROP_SIZE))
        meta["crop_size"] = CROP_SIZE
    else:
        logger.warning("Image is %dx%d, smaller than %dx%d — sending as-is", w, h, CROP_SIZE, CROP_SIZE)

    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue(), meta


# ── PlantNet API helpers ───────────────────────────────────────────────────────

def call_embeddings_api(jpeg_bytes: bytes, filename: str, api_key: str) -> dict:
    files = [("image", (filename, io.BytesIO(jpeg_bytes), "image/jpeg"))]
    params = {"api-key": api_key}
    resp = requests.post(PLANTNET_API_URL, files=files, params=params, timeout=API_TIMEOUT)
    if resp.status_code == 429:
        raise QuotaExceededError(f"PlantNet daily quota exceeded (HTTP 429): {resp.text}")
    resp.raise_for_status()
    return resp.json()


def extract_embedding(api_response: dict) -> tuple:
    """Return (embedding_list, version_str). Handles flat and tile-style responses."""
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
            dims = len(val[0]["embeddings"])
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
            f"Could not find embedding in API response. Keys: {list(api_response.keys())}."
        )

    version = None
    for key in ("version", "plantnet_version", "model_version", "model"):
        if key in api_response and isinstance(api_response[key], str):
            version = api_response[key]
            break

    return embedding, version


def parse_version_slug(api_version_str: str | None) -> str:
    """'2026-02-17 (7.4)' → 'v7.4'.  Returns 'unknown' if unparseable."""
    if not api_version_str:
        return "unknown"
    m = re.search(r"\((\d+\.\d+)\)", api_version_str)
    return f"v{m.group(1)}" if m else "unknown"


# ── Cache / status helpers ─────────────────────────────────────────────────────

def load_cache(cache_dir: Path, data_row_id: str, version_slug: str) -> dict | None:
    path = cache_dir / f"{data_row_id}_{version_slug}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_cache(cache_dir: Path, data_row_id: str, entry: dict, version_slug: str):
    path = cache_dir / f"{data_row_id}_{version_slug}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(entry, f)
    tmp.replace(path)


def load_status(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_status(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


# ── Labelbox helpers ───────────────────────────────────────────────────────────

def find_dataset_by_name(client: lb.Client, name: str):
    """Return dataset whose name is exactly `name`, or None."""
    for d in client.get_datasets():
        if d.name == name:
            return d
    return None


def export_dataset_rows(dataset, verbose: bool = False) -> list[dict]:
    if verbose:
        logger.info("Exporting data rows from '%s'...", dataset.name)

    export_task = dataset.export(params={
        "attachments": False,
        "metadata_fields": False,
        "data_row_details": True,
        "embeddings": False,
        "labels": False,
    })
    export_task.wait_till_done(timeout_seconds=EXPORT_TIMEOUT_SEC)

    try:
        errors = []
        export_task.get_buffered_stream(stream_type=lb.StreamType.ERRORS).start(
            stream_handler=lambda o: errors.append(o.json)
        )
        if errors:
            logger.warning("Export errors: %s", errors)
    except ValueError:
        pass

    rows = []

    def _collect(output):
        dr = output.json.get("data_row", {})
        if dr.get("id") and dr.get("row_data"):
            rows.append({
                "data_row_id": dr["id"],
                "global_key": dr.get("global_key", ""),
                "image_url": dr["row_data"],
            })

    export_task.get_buffered_stream(stream_type=lb.StreamType.RESULT).start(
        stream_handler=_collect
    )

    logger.info("Found %d data rows", len(rows))
    return rows


def get_or_create_embedding(client: lb.Client, name: str, dims: int):
    for emb in client.get_embeddings():
        if emb.name == name and emb.custom:
            if emb.dims != dims:
                logger.error("Existing embedding '%s' has dims=%d, expected %d.", name, emb.dims, dims)
                sys.exit(1)
            logger.info("Using existing embedding '%s' (id=%s)", name, emb.id)
            return emb
    logger.info("Creating new custom embedding '%s' (dims=%d)...", name, dims)
    emb = client.create_embedding(name=name, dims=dims)
    logger.info("Created embedding id=%s", emb.id)
    return emb


def upload_vectors(embedding, vectors: list[dict]):
    ndjson_lines = "\n".join(json.dumps(v) for v in vectors)
    batch_count = 0

    def on_batch(_):
        nonlocal batch_count
        batch_count += 1
        logger.info("  Batch %d accepted", batch_count)

    embedding.import_vectors_from_file(io.BytesIO(ndjson_lines.encode()), callback=on_batch)


# ── Version probe ──────────────────────────────────────────────────────────────

def probe_version(
    row: dict,
    cache_dir: Path,
    api_key: str,
    verbose: bool,
) -> tuple[str, str, dict]:
    """
    Call the PlantNet API with `row` to discover the current model version.
    Saves the result to cache and returns (version_slug, embedding_name, vector).
    """
    dr_id = row["data_row_id"]
    if verbose:
        logger.info("Probing API version with row %s...", dr_id)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            image_bytes = download_image_to_memory(row["image_url"])
            jpeg_bytes, crop_meta = center_crop_to_jpeg(image_bytes)
            api_response = call_embeddings_api(jpeg_bytes, dr_id, api_key)
            embedding_vec, api_version_str = extract_embedding(api_response)
            break
        except QuotaExceededError:
            raise
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = [1, 5, 10][attempt - 1]
                logger.warning("Probe attempt %d/%d failed: %s. Retrying in %ds...", attempt, MAX_RETRIES, e, wait)
                time.sleep(wait)
            else:
                logger.error("Could not probe API version after %d attempts: %s", MAX_RETRIES, e)
                sys.exit(1)

    version_slug = parse_version_slug(api_version_str)
    embedding_name = EMBEDDING_NAME_TEMPLATE.format(version=version_slug)
    logger.info("API version: %s  →  slug=%s  →  name=%s", api_version_str, version_slug, embedding_name)

    entry = {
        "data_row_id": dr_id,
        "global_key": row["global_key"],
        "image_url": row["image_url"],
        "embedding": embedding_vec,
        "original_width": crop_meta["original_width"],
        "original_height": crop_meta["original_height"],
        "crop_size": crop_meta["crop_size"],
        "plantnet_version": api_version_str,
    }
    save_cache(cache_dir, dr_id, entry, version_slug)

    return version_slug, embedding_name, {"id": dr_id, "vector": embedding_vec}


# ── Core processing ────────────────────────────────────────────────────────────

def process_rows(
    rows: list[dict],
    probe_vector: dict,
    cache_dir: Path,
    plantnet_api_key: str,
    version_slug: str,
    delay: float,
    verbose: bool,
) -> tuple[list[dict], bool]:
    """
    Fetch embeddings for every row not yet cached at `version_slug`.
    `probe_vector` is the vector already obtained for rows[0]; included
    immediately so the main loop skips that row.
    Returns (all_vectors, quota_hit).
    """
    cached = sum(1 for r in rows if load_cache(cache_dir, r["data_row_id"], version_slug) is not None)
    logger.info("Total: %d, already cached: %d, to process: %d", len(rows), cached, len(rows) - cached)

    vectors: list[dict] = [probe_vector]

    for i, row in enumerate(rows, 1):
        dr_id = row["data_row_id"]

        if dr_id == probe_vector["id"]:
            continue

        cached_entry = load_cache(cache_dir, dr_id, version_slug)
        if cached_entry is not None:
            vectors.append({"id": dr_id, "vector": cached_entry["embedding"]})
            continue

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if verbose:
                    logger.info("[%d/%d] Downloading %s...", i, len(rows), row["image_url"][:80])
                image_bytes = download_image_to_memory(row["image_url"])
                jpeg_bytes, crop_meta = center_crop_to_jpeg(image_bytes)

                if verbose:
                    logger.info("Crop: %s, JPEG: %d bytes", crop_meta["crop_size"], len(jpeg_bytes))

                api_response = call_embeddings_api(jpeg_bytes, dr_id, plantnet_api_key)

                if verbose:
                    resp_str = json.dumps(api_response, indent=2)
                    logger.info("API response:\n%s%s", resp_str[:2000], "..." if len(resp_str) > 2000 else "")

                embedding_vec, api_version_str = extract_embedding(api_response)
                entry = {
                    "data_row_id": dr_id,
                    "global_key": row["global_key"],
                    "image_url": row["image_url"],
                    "embedding": embedding_vec,
                    "original_width": crop_meta["original_width"],
                    "original_height": crop_meta["original_height"],
                    "crop_size": crop_meta["crop_size"],
                    "plantnet_version": api_version_str,
                }
                save_cache(cache_dir, dr_id, entry, version_slug)
                vectors.append({"id": dr_id, "vector": embedding_vec})
                success = True
                break

            except QuotaExceededError as e:
                logger.warning("PlantNet daily quota exceeded after %d new rows processed.", i - 1)
                logger.warning("%s", e)
                logger.warning(
                    "%d vectors ready (including previously cached). Uploading and stopping.", len(vectors)
                )
                logger.warning("Re-run tomorrow to process the remaining rows.")
                return vectors, True

            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = [1, 5, 10][attempt - 1]
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s. Retrying in %ds...", attempt, MAX_RETRIES, dr_id, e, wait
                    )
                    time.sleep(wait)
                else:
                    logger.error("FAILED after %d attempts for %s: %s", MAX_RETRIES, dr_id, e)

        if success and i < len(rows):
            time.sleep(delay)

        if not verbose and (i % 100 == 0 or i == len(rows)):
            logger.info("[%d/%d] vectors ready=%d", i, len(rows), len(vectors))

    return vectors, False


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    project_root = Path(__file__).parent.parent.parent

    parser = argparse.ArgumentParser(
        description="Get PlantNet embeddings for a Labelbox project dataset and upload them."
    )
    parser.add_argument(
        "--project", required=True,
        help="Project name (e.g. '2024_bci'); dataset in Labelbox must have exactly this name",
    )
    parser.add_argument(
        "--test-one", action="store_true",
        help="Process only the first data row (verbose, for debugging)",
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Delay in seconds between PlantNet API calls (default: {DEFAULT_DELAY})",
    )
    args = parser.parse_args()

    load_dotenv(dotenv_path=project_root / ".env")

    cache_dir = project_root / "projects" / args.project / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    status_path = project_root / "projects" / args.project / "embeddings_status.json"

    plantnet_api_key = os.environ.get("PLANTNET_API_KEY")
    if not plantnet_api_key:
        logger.error("PLANTNET_API_KEY not found in .env")
        sys.exit(1)

    labelbox_api_key = os.environ.get("LABELBOX_API_KEY")
    if not labelbox_api_key:
        logger.error("LABELBOX_API_KEY not found in .env")
        sys.exit(1)

    # ── Labelbox dataset ───────────────────────────────────────────────────────
    client = lb.Client(api_key=labelbox_api_key)

    logger.info("Looking for Labelbox dataset named exactly '%s'...", args.project)
    dataset = find_dataset_by_name(client, args.project)
    if dataset is None:
        logger.error("No dataset found with name '%s'.", args.project)
        sys.exit(1)
    logger.info("Found: %s  (id: %s)", dataset.name, dataset.uid)

    # ── Export rows ────────────────────────────────────────────────────────────
    logger.info("Exporting dataset rows...")
    rows = export_dataset_rows(dataset, verbose=args.test_one)
    if not rows:
        logger.error("Dataset is empty.")
        sys.exit(1)

    if args.test_one:
        rows = rows[:1]
        logger.info("TEST-ONE: processing 1 data row only")

    # ── Version probe ──────────────────────────────────────────────────────────
    logger.info("Probing PlantNet API version...")
    prev_status = load_status(status_path)
    try:
        version_slug, embedding_name, probe_vector = probe_version(
            row=rows[0],
            cache_dir=cache_dir,
            api_key=plantnet_api_key,
            verbose=args.test_one,
        )
    except QuotaExceededError as e:
        logger.error("PlantNet quota already exhausted — cannot probe version. Re-run tomorrow.\n%s", e)
        sys.exit(1)

    if prev_status.get("version_slug") and prev_status["version_slug"] != version_slug:
        logger.info(
            "API version changed from %s to %s — all rows will be reprocessed for the new version.",
            prev_status["version_slug"], version_slug,
        )

    # ── Labelbox embedding ─────────────────────────────────────────────────────
    logger.info("Setting up Labelbox embedding '%s'...", embedding_name)
    lb_embedding = get_or_create_embedding(client, embedding_name, EMBEDDING_DIMS)

    # ── Process remaining rows ─────────────────────────────────────────────────
    logger.info("Processing embeddings...")
    vectors, quota_hit = process_rows(
        rows=rows,
        probe_vector=probe_vector,
        cache_dir=cache_dir,
        plantnet_api_key=plantnet_api_key,
        version_slug=version_slug,
        delay=args.delay,
        verbose=args.test_one,
    )

    # ── Upload ─────────────────────────────────────────────────────────────────
    if vectors:
        logger.info("Uploading %d vector(s) to Labelbox...", len(vectors))
        upload_vectors(lb_embedding, vectors)
        logger.info("Upload submitted.")
    else:
        logger.info("No vectors to upload.")

    # ── Status ─────────────────────────────────────────────────────────────────
    completed = sum(
        1 for r in rows
        if load_cache(cache_dir, r["data_row_id"], version_slug) is not None
    )
    all_complete = completed == len(rows) and not args.test_one

    save_status(status_path, {
        "project": args.project,
        "embedding_name": embedding_name,
        "version_slug": version_slug,
        "dataset_name": dataset.name,
        "dataset_id": dataset.uid,
        "total_rows": len(rows),
        "completed_rows": completed,
        "all_complete": all_complete,
        "last_run": datetime.now().isoformat(),
    })
    logger.info("Status written to %s", status_path.relative_to(project_root))

    # ── Summary ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  Project:    %s", args.project)
    logger.info("  Dataset:    %s  (id=%s)", dataset.name, dataset.uid)
    logger.info("  Embedding:  %s  (id=%s)", embedding_name, lb_embedding.id)
    logger.info("  Rows total: %d", len(rows))
    logger.info("  Completed:  %d", completed)
    logger.info("  All done:   %s", all_complete)
    logger.info("=" * 60)

    if quota_hit:
        logger.warning("Daily quota reached. Re-run tomorrow to finish the remaining rows.")
        sys.exit(1)


if __name__ == "__main__":
    main()
