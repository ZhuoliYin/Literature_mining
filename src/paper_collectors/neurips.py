from __future__ import annotations

import time
from urllib.parse import urljoin

import requests

from .common import Paper, clean_text, get_html, logger, meta_list, progress


def _neurips_index_candidates(year: int) -> list[str]:
    if year <= 2017:
        return [
            f"https://papers.nips.cc/paper/{year}",
            f"https://papers.nips.cc/paper_files/paper/{year}",
        ]
    return [
        f"https://proceedings.neurips.cc/paper_files/paper/{year}",
        f"https://papers.nips.cc/paper_files/paper/{year}",
    ]


def _load_neurips_index(year: int):
    for index_url in _neurips_index_candidates(year):
        try:
            index = get_html(index_url)
            logger.info("NeurIPS index URL selected for %d: %s", year, index_url)
            return index_url, index
        except requests.RequestException:
            continue
    raise requests.RequestException(f"No reachable NeurIPS index URL for year {year}")


def collect_neurips_proceedings(year: int) -> list[Paper]:
    index_url, index = _load_neurips_index(year)
    papers: list[Paper] = []
    seen: set[str] = set()

    anchors = index.select("a[href*='Abstract'][href$='.html']")
    for anchor in progress(anchors, desc="NeurIPS proc", total=len(anchors)):
        href = anchor.get("href", "")
        if not href:
            continue
        paper_url = urljoin(index_url + "/", href)
        if paper_url in seen:
            continue
        seen.add(paper_url)

        page = get_html(paper_url)
        title = clean_text((meta_list(page, "citation_title") or [anchor.get_text(" ", strip=True)])[0])
        abstract = clean_text(" ".join(meta_list(page, "description")))
        authors = meta_list(page, "citation_author")

        pdf_link = page.select_one("a[href$='.pdf']")
        pdf = urljoin(paper_url, pdf_link.get("href", "")) if pdf_link else None

        papers.append(
            Paper(
                conference="NEURIPS",
                year=year,
                title=title,
                abstract=abstract,
                authors=authors,
                paper_url=paper_url,
                pdf_url=pdf,
                source="neurips_proceedings",
            )
        )
        time.sleep(0.08)

    return papers
