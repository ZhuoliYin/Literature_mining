from __future__ import annotations

import time

from .common import Paper, clean_text, get_html, logger, meta_list, progress


def _find_icml_volume(year: int) -> str | None:
    soup = get_html("https://proceedings.mlr.press/")
    for card in soup.select("li"):
        text = clean_text(card.get_text(" ", strip=True))
        if "International Conference on Machine Learning" not in text:
            continue
        if str(year) not in text:
            continue
        link = card.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        return href if href.startswith("http") else f"https://proceedings.mlr.press/{href.lstrip('/')}"
    return None


def collect_icml_pmlr(year: int) -> list[Paper]:
    volume_url = _find_icml_volume(year)
    logger.info("PMLR volume URL for ICML %d: %s", year, volume_url or "<none>")
    if not volume_url:
        return []

    volume_prefix = volume_url.rstrip("/") + "/"
    volume = get_html(volume_url)
    papers: list[Paper] = []

    anchors = volume.select("a[href$='.html']")
    for anchor in progress(anchors, desc="PMLR/ICML", total=len(anchors)):
        href = anchor.get("href", "")
        if not href or href.endswith("index.html"):
            continue
        paper_url = f"{volume_url.rstrip('/')}/{href.lstrip('./')}" if not href.startswith("http") else href

        if not paper_url.startswith(volume_prefix):
            continue

        page = get_html(paper_url)
        conf_meta = meta_list(page, "citation_conference_title")
        if conf_meta:
            low = conf_meta[0].lower()
            if "machine learning" not in low and "icml" not in low:
                continue

        title_node = page.find("h1") or page.find("title")
        title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        abs_node = page.find(id="abstract") or page.select_one("div.abstract") or page.select_one("p.abstract")
        abstract = clean_text(abs_node.get_text(" ", strip=True) if abs_node else "")
        authors = [a for a in meta_list(page, "citation_author") if a]

        pdf_meta = page.find("meta", attrs={"name": "citation_pdf_url"})
        pdf = pdf_meta.get("content") if pdf_meta else None

        papers.append(
            Paper(
                conference="ICML",
                year=year,
                title=title,
                abstract=abstract,
                authors=authors,
                paper_url=paper_url,
                pdf_url=pdf,
                source="pmlr",
            )
        )
        time.sleep(0.1)

    return list({p.paper_url: p for p in papers}.values())
