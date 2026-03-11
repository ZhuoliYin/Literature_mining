from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .common import Paper


def write_jsonl(papers: Iterable[Paper], output: Path) -> None:
    with output.open("w", encoding="utf-8") as handle:
        for paper in papers:
            handle.write(json.dumps(asdict(paper), ensure_ascii=False) + "\n")


def write_csv(papers: Iterable[Paper], output: Path) -> None:
    fields = list(Paper.__dataclass_fields__)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for paper in papers:
            row = asdict(paper)
            row["authors"] = "; ".join(row["authors"])
            writer.writerow(row)
