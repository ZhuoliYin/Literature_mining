from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from .common import Paper, clean_text, get_html, logger, meta_list, progress


def collect_acl_anthology(year: int) -> list[Paper]:
    event_url = f"https://aclanthology.org/events/acl-{year}/"
    logger.info("ACL event URL for %d: %s", year, event_url)
    event = get_html(event_url)
    papers: list[Paper] = []
    seen: set[str] = set()
    pattern = re.compile(rf"^/{year}\.acl[\w.-]*\.\d+/$")

    for anchor in progress(event.select("a[href]"), desc="ACL Anthology"):
        href = anchor.get("href", "")
        if not pattern.match(href):
            continue
        paper_url = urljoin(event_url, href)
        if paper_url in seen:
            continue
        seen.add(paper_url)

        page = get_html(paper_url)
        title = clean_text((meta_list(page, "citation_title") or [anchor.get_text(" ", strip=True)])[0])
        abstract = clean_text(" ".join(meta_list(page, "description")))
        if not abstract:
            abs_node = page.select_one("div.acl-abstract")
            abstract = clean_text(abs_node.get_text(" ", strip=True) if abs_node else "")
        authors = meta_list(page, "citation_author")

        pdf_meta = meta_list(page, "citation_pdf_url")
        pdf = pdf_meta[0] if pdf_meta else None

        papers.append(
            Paper(
                conference="ACL",
                year=year,
                title=title,
                abstract=abstract,
                authors=authors,
                paper_url=paper_url,
                pdf_url=pdf,
                source="acl_anthology",
            )
        )
        time.sleep(0.08)

    return papers
