from __future__ import annotations

import time
from pathlib import Path

import requests

from .common import Paper, USER_AGENT, progress, safe_filename


def download_pdfs(papers: list[Paper], pdf_dir: Path) -> tuple[int, int, int]:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = failed = 0

    for idx, paper in progress(enumerate(papers, 1), desc="Downloading PDFs", total=len(papers)):
        if not paper.pdf_url:
            skipped += 1
            continue

        filename = f"{idx:04d}_{safe_filename(paper.title)}.pdf"
        pdf_path = pdf_dir / filename
        if pdf_path.exists():
            skipped += 1
            continue

        try:
            resp = requests.get(paper.pdf_url, timeout=45, headers={"User-Agent": USER_AGENT}, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not paper.pdf_url.lower().endswith(".pdf"):
                failed += 1
                continue

            with pdf_path.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
            downloaded += 1
            time.sleep(0.05)
        except requests.RequestException:
            failed += 1

    return downloaded, skipped, failed
