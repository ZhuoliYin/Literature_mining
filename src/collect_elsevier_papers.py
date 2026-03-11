#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests

BASE_SEARCH_URL = "https://api.elsevier.com/content/search/sciencedirect"
BASE_ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi"
USER_AGENT = "auto-literature-review/0.1"


@dataclass
class ElsevierPaper:
    title: str
    abstract: str
    doi: str
    pii: str
    publication_name: str
    publication_date: str
    authors: list[str]
    paper_url: str
    source: str


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def build_headers(api_key: str, insttoken: str | None = None) -> dict[str, str]:
    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken
    return headers


def fetch_json(url: str, headers: dict[str, str], params: dict | None = None) -> dict:
    response = requests.get(url, headers=headers, params=params, timeout=45)
    response.raise_for_status()
    return response.json()


def _parse_authors(entry: dict) -> list[str]:
    authors = entry.get("authors", [])
    names = []
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, dict):
                continue
            name = clean_text(author.get("name"))
            if name:
                names.append(name)
    return names


def search_sciencedirect(
    query: str,
    year_from: int | None,
    year_to: int | None,
    api_key: str,
    insttoken: str | None,
    max_results: int,
    include_abstract: bool,
    sleep_seconds: float,
) -> list[ElsevierPaper]:
    headers = build_headers(api_key, insttoken)
    offset = 0
    count = min(100, max_results)
    papers: list[ElsevierPaper] = []

    while len(papers) < max_results:
        params: dict[str, str | int] = {
            "query": query,
            "count": count,
            "start": offset,
        }
        if year_from is not None:
            params["date"] = f"{year_from}-{year_to if year_to is not None else year_from}"

        payload = fetch_json(BASE_SEARCH_URL, headers, params=params)
        entries = payload.get("search-results", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            title = clean_text(entry.get("dc:title"))
            doi = clean_text(entry.get("prism:doi"))
            pii = clean_text(entry.get("pii"))
            publication_name = clean_text(entry.get("prism:publicationName"))
            publication_date = clean_text(entry.get("prism:coverDate"))
            paper_url = clean_text(entry.get("link", [{}])[0].get("@href")) if entry.get("link") else ""
            authors = _parse_authors(entry)
            abstract = clean_text(entry.get("dc:description"))

            papers.append(
                ElsevierPaper(
                    title=title,
                    abstract=abstract,
                    doi=doi,
                    pii=pii,
                    publication_name=publication_name,
                    publication_date=publication_date,
                    authors=authors,
                    paper_url=paper_url,
                    source="elsevier_sciencedirect",
                )
            )

            if len(papers) >= max_results:
                break

        offset += len(entries)
        if len(entries) < count:
            break
        time.sleep(sleep_seconds)

    if include_abstract:
        enrich_abstracts_with_doi(papers, headers, sleep_seconds)

    return papers


def enrich_abstracts_with_doi(
    papers: list[ElsevierPaper], headers: dict[str, str], sleep_seconds: float
) -> None:
    for paper in papers:
        if paper.abstract:
            continue
        if not paper.doi:
            continue
        doi_path = quote(paper.doi, safe="")
        url = f"{BASE_ABSTRACT_URL}/{doi_path}"
        try:
            payload = fetch_json(url, headers, params=None)
        except requests.RequestException:
            continue

        coredata = payload.get("abstracts-retrieval-response", {}).get("coredata", {})
        description = clean_text(coredata.get("dc:description"))
        if description:
            paper.abstract = description
        time.sleep(sleep_seconds)


def write_jsonl(rows: Iterable[ElsevierPaper], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def write_csv(rows: Iterable[ElsevierPaper], output_path: Path) -> None:
    fields = [
        "title",
        "abstract",
        "doi",
        "pii",
        "publication_name",
        "publication_date",
        "authors",
        "paper_url",
        "source",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row_dict = asdict(row)
            row_dict["authors"] = "; ".join(row_dict["authors"])
            writer.writerow(row_dict)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect papers from Elsevier ScienceDirect via official Elsevier APIs."
    )
    parser.add_argument("--query", required=True, help='Query string, e.g. "transformer AND reinforcement learning"')
    parser.add_argument("--year-from", type=int, default=None, help="Start year (optional)")
    parser.add_argument("--year-to", type=int, default=None, help="End year (optional)")
    parser.add_argument("--max-results", type=int, default=200, help="Maximum papers to collect")
    parser.add_argument("--include-abstract", action="store_true", help="Try DOI abstract enrichment if search abstracts are missing")
    parser.add_argument("--sleep-seconds", type=float, default=0.2, help="Delay between API requests")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl", help="Output format")
    parser.add_argument(
        "--api-key",
        default=os.getenv("ELSEVIER_API_KEY", ""),
        help="Elsevier API key (or set ELSEVIER_API_KEY env var)",
    )
    parser.add_argument(
        "--insttoken",
        default=os.getenv("ELSEVIER_INSTTOKEN", ""),
        help="Elsevier institutional token (optional, or set ELSEVIER_INSTTOKEN)",
    )
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit(
            "Missing API key. Set --api-key or export ELSEVIER_API_KEY first."
        )

    papers = search_sciencedirect(
        query=args.query,
        year_from=args.year_from,
        year_to=args.year_to,
        api_key=args.api_key,
        insttoken=args.insttoken or None,
        max_results=args.max_results,
        include_abstract=args.include_abstract,
        sleep_seconds=max(0.0, args.sleep_seconds),
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "jsonl":
        write_jsonl(papers, output_path)
    else:
        write_csv(papers, output_path)

    print(f"Collected {len(papers)} papers -> {output_path}")


if __name__ == "__main__":
    main()
