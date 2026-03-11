#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from paper_collectors import (
    CONFERENCE_SOURCES,
    collect,
    download_pdfs,
    set_show_progress,
    write_csv,
    write_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_project_data_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return PROJECT_ROOT / path
    return path


def main() -> None:
    supported = sorted(CONFERENCE_SOURCES)

    parser = argparse.ArgumentParser(
        description=(
            "Collect accepted papers from top AI conferences. "
            "OpenReview is always tried first; proceedings sites are used as fallback."
        )
    )
    parser.add_argument(
        "--conference",
        required=True,
        help=f"Conference key: {', '.join(c.upper() for c in supported)}",
    )
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--output", required=True, help="Output file (e.g. data/iclr_2024.jsonl at project root)")
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    parser.add_argument(
        "--source",
        default="auto",
        choices=[
            "auto",
            "openreview",
            "iclr_archive",
            "pmlr",
            "neurips_proceedings",
            "aaai_ojs",
            "acl_anthology",
            "ijcai_proceedings",
        ],
        help="Force a specific source (default: auto = OpenReview first)",
    )
    parser.add_argument("--download-pdfs", action="store_true", help="Download PDFs after collecting metadata")
    parser.add_argument("--pdf-dir", default=None, help="PDF download directory")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--include-submissions", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    set_show_progress(not args.no_progress)

    papers = collect(args.conference, args.year, source=args.source)

    output_path = _resolve_project_data_path(args.output)
    assert output_path is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "jsonl":
        write_jsonl(papers, output_path)
    else:
        write_csv(papers, output_path)

    print(f"\nCollected {len(papers)} papers -> {output_path}")

    if args.download_pdfs:
        pdf_dir = (
            _resolve_project_data_path(args.pdf_dir)
            if args.pdf_dir
            else output_path.parent / f"{output_path.stem}_pdfs"
        )
        assert pdf_dir is not None
        downloaded, skipped, failed = download_pdfs(papers, pdf_dir)
        print(f"PDFs: downloaded={downloaded}  skipped={skipped}  failed={failed} -> {pdf_dir}")


if __name__ == "__main__":
    main()
