import dataclasses
import datetime as dt
import json
import logging
import os
from typing import Iterable, List, Dict, Any, Optional

import requests

# ---- Logging setup ---------------------------------------------------------


LOG_LEVEL = os.getenv("JOBTRACKER_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---- Domain model ----------------------------------------------------------


@dataclasses.dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    remote: bool
    posted_at: Optional[str] = None
    raw: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


TARGET_KEYWORDS = [
    "devops",
    "site reliability",
    "sre",
    "cloud engineer",
    "platform engineer",
    "infrastructure",
]


def _matches_keywords(title: str) -> bool:
    title_lower = title.lower()
    return any(k in title_lower for k in TARGET_KEYWORDS)


def _looks_remote(location: str) -> bool:
    loc = (location or "").lower()
    return any(word in loc for word in ["remote", "anywhere", "distributed"])


# ---- Source definitions (API-based where possible) -------------------------


@dataclasses.dataclass
class Source:
    name: str
    type: str  # "greenhouse", "lever", "misc"
    config: Dict[str, Any]


# Example: You can add your target companies here instead of editing code logic
COMPANY_SOURCES: List[Source] = [
    # Greenhouse example
    Source(
        name="ExampleCo",
        type="greenhouse",
        config={"board_token": "exampleco"},
    ),
    # Lever example
    Source(
        name="AnotherCo",
        type="lever",
        config={"company": "anotherco"},
    ),
    # You can add more types later ("ashby", "workable", "custom_json", etc.)
]


# ---- Fetchers --------------------------------------------------------------


def fetch_from_greenhouse(source: Source) -> Iterable[Job]:
    board_token = source.config["board_token"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    logger.info("Fetching Greenhouse jobs for %s (%s)", source.name, url)

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("jobs", []):
        title = item.get("title", "")
        location = item.get("location", {}).get("name", "") or ""
        job_url = item.get("absolute_url", "")

        if not _matches_keywords(title):
            continue

        job = Job(
            source="greenhouse",
            company=source.name,
            title=title,
            location=location,
            url=job_url,
            remote=_looks_remote(location),
            posted_at=item.get("updated_at"),
            raw=item,
        )
        yield job


def fetch_from_lever(source: Source) -> Iterable[Job]:
    company = source.config["company"]
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    logger.info("Fetching Lever jobs for %s (%s)", source.name, url)

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for item in data:
        title = item.get("text", "")
        location = ", ".join(item.get("categories", {}).get("location", "").split("/"))
        job_url = item.get("hostedUrl") or item.get("applyUrl", "")

        if not _matches_keywords(title):
            continue

        job = Job(
            source="lever",
            company=source.name,
            title=title,
            location=location,
            url=job_url,
            remote=_looks_remote(location),
            posted_at=item.get("createdAt"),
            raw=item,
        )
        yield job


def fetch_from_source(source: Source) -> Iterable[Job]:
    try:
        if source.type == "greenhouse":
            yield from fetch_from_greenhouse(source)
        elif source.type == "lever":
            yield from fetch_from_lever(source)
        else:
            logger.warning("Unknown source type '%s' for %s", source.type, source.name)
    except Exception as exc:
        logger.exception("Failed to fetch jobs for %s: %s", source.name, exc)


# ---- Aggregation / output --------------------------------------------------


def dedupe_jobs(jobs: Iterable[Job]) -> List[Job]:
    seen = set()
    deduped: List[Job] = []
    for job in jobs:
        key = (job.company.lower(), job.title.lower(), job.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def save_jobs_json(jobs: List[Job], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([j.to_dict() for j in jobs], f, indent=2, ensure_ascii=False)
    logger.info("Saved %d jobs to %s", len(jobs), path)


def main() -> None:
    logger.info("Starting job fetch")

    all_jobs: List[Job] = []

    for src in COMPANY_SOURCES:
        jobs = list(fetch_from_source(src))
        logger.info("Fetched %d jobs from %s", len(jobs), src.name)
        all_jobs.extend(jobs)

    filtered = [j for j in all_jobs if j.remote]  # remote only
    deduped = dedupe_jobs(filtered)

    logger.info(
        "Total fetched: %d, after remote filter: %d, after dedupe: %d",
        len(all_jobs),
        len(filtered),
        len(deduped),
    )

    today = dt.date.today().isoformat()
    output_path = os.path.join(
        os.path.dirname(__file__),
        "data",
        f"jobs_{today}.json",
    )
    save_jobs_json(deduped, output_path)


if __name__ == "__main__":
    main()
