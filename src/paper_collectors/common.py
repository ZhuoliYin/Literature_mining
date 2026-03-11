from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

USER_AGENT = "paper-collector/0.2 (+https://github.com/)"
logger = logging.getLogger(__name__)
SHOW_PROGRESS = True


@dataclass
class Paper:
    conference: str
    year: int
    title: str
    abstract: str
    authors: list[str]
    paper_url: str
    pdf_url: str | None
    source: str


def set_show_progress(enabled: bool) -> None:
    global SHOW_PROGRESS
    SHOW_PROGRESS = enabled


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def get_json(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.json()


def get_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return BeautifulSoup(resp.text, "html.parser")


def meta_list(soup: BeautifulSoup, name: str) -> list[str]:
    values = [clean_text(n.get("content", "")) for n in soup.find_all("meta", attrs={"name": name})]
    return [v for v in values if v]


def progress(iterable, desc: str, total: int | None = None):
    return tqdm(iterable, desc=desc, total=total, disable=not SHOW_PROGRESS, dynamic_ncols=True)


def safe_filename(text: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"[^\w\s.-]", "", clean_text(text))
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    return (cleaned or "paper")[:max_len]


def try_collect(collector, *args) -> list[Paper]:
    try:
        return collector(*args)
    except requests.RequestException as exc:
        logger.warning("Collector %s(%s) failed: %s", collector.__name__, args, exc)
        return []
