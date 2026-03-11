from __future__ import annotations

import re

from .common import Paper, clean_text, get_html, logger


def _arxiv_pdf_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.match(r"https?://arxiv\.org/abs/([^?#]+)", url)
    if not match:
        return None
    return f"https://arxiv.org/pdf/{match.group(1)}.pdf"


def _split_authors(authors_text: str) -> list[str]:
    authors_text = clean_text(authors_text)
    if not authors_text:
        return []
    normalized = authors_text.replace(" and ", ", ")
    parts = [clean_text(part) for part in normalized.split(",")]
    return [part for part in parts if part]


def collect_iclr_archive(year: int) -> list[Paper]:
    if year not in {2015, 2016}:
        return []

    archive_url = f"https://iclr.cc/archive/www/{year}.html"
    logger.info("ICLR archive URL for %d: %s", year, archive_url)
    soup = get_html(archive_url)

    if year == 2015:
        return _collect_iclr_2015(soup)
    return _collect_iclr_2016(soup)


def _collect_iclr_2015(soup) -> list[Paper]:
    papers: list[Paper] = []
    oral_heading = soup.find(id="conference_oral_presentations")
    if oral_heading:
        oral_section = oral_heading.find_next("div")
        if oral_section:
            oral_list = oral_section.find("ul")
            if oral_list:
                for item in oral_list.find_all("li", recursive=False):
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    title = clean_text(link.get_text(" ", strip=True))
                    item_text = clean_text(item.get_text(" ", strip=True))
                    authors_text = clean_text(item_text[len(title):]).lstrip(", ")
                    papers.append(
                        Paper(
                            conference="ICLR",
                            year=2015,
                            title=title,
                            abstract="",
                            authors=_split_authors(authors_text),
                            paper_url=link["href"],
                            pdf_url=_arxiv_pdf_url(link["href"]),
                            source="iclr_archive",
                        )
                    )

    poster_heading = soup.find(id="may_9_conference_poster_session")
    if poster_heading:
        poster_section = poster_heading.find_next("div")
        if poster_section:
            for row in poster_section.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                link = row.find("a", href=True)
                if not link:
                    continue

                title = clean_text(link.get_text(" ", strip=True))
                cell_text = clean_text(cells[1].get_text(" ", strip=True))
                authors_text = clean_text(cell_text[len(title):]).lstrip(", ")

                papers.append(
                    Paper(
                        conference="ICLR",
                        year=2015,
                        title=title,
                        abstract="",
                        authors=_split_authors(authors_text),
                        paper_url=link["href"],
                        pdf_url=_arxiv_pdf_url(link["href"]),
                        source="iclr_archive",
                    )
                )

    dedup: dict[str, Paper] = {}
    for paper in papers:
        dedup[paper.title] = paper
    return list(dedup.values())


def _collect_iclr_2016(soup) -> list[Paper]:
    heading = soup.find(string=lambda s: s and "Accepted Papers (Conference Track)" in s)
    if not heading:
        return []

    section = heading.parent.find_next("div")
    if not section:
        return []

    accepted_list = section.find("ol")
    if not accepted_list:
        return []

    papers: list[Paper] = []
    for item in accepted_list.find_all("li", recursive=False):
        link = item.find("a", href=True)
        if not link:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        item_text = clean_text(item.get_text(" ", strip=True))
        authors_text = clean_text(item_text[len(title):]).lstrip(", ")

        papers.append(
            Paper(
                conference="ICLR",
                year=2016,
                title=title,
                abstract="",
                authors=_split_authors(authors_text),
                paper_url=link["href"],
                pdf_url=_arxiv_pdf_url(link["href"]),
                source="iclr_archive",
            )
        )

    return papers
