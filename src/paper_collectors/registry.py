from __future__ import annotations

from typing import Callable

from .aaai import collect_aaai_ojs
from .acl import collect_acl_anthology
from .common import Paper, logger, try_collect
from .iclr_archive import collect_iclr_archive
from .ijcai import collect_ijcai_proceedings
from .neurips import collect_neurips_proceedings
from .openreview import collect_openreview
from .pmlr import collect_icml_pmlr

CONFERENCE_SOURCES: dict[str, list[tuple[Callable, Callable[[int], tuple]]]] = {
    # Reference registry used for CLI supported conference list.
    "iclr": [],
    "icml": [],
    "neurips": [],
    "aaai": [],
    "acl": [],
    "ijcai": [],
    "chi": []
}


def source_plan(conf_key: str, year: int) -> list[tuple[Callable, tuple]]:
    """Year-aware source routing based on conference hosting transitions."""
    if conf_key == "iclr":
        if year in {2015, 2016}:
            return [(collect_iclr_archive, (year,))]
        return [(collect_openreview, ("iclr", year))]

    if conf_key == "icml":
        if year >= 2023:
            return [
                (collect_openreview, ("icml", year)),
                (collect_icml_pmlr, (year,)),
            ]
        return [(collect_icml_pmlr, (year,))]

    if conf_key == "neurips":
        if year >= 2021:
            return [
                (collect_openreview, ("neurips", year)),
                (collect_neurips_proceedings, (year,)),
            ]
        return [(collect_neurips_proceedings, (year,))]

    if conf_key == "aaai":
        if year >= 2025:
            return [
                (collect_openreview, ("aaai", year)),
                (collect_aaai_ojs, (year,)),
            ]
        return [(collect_aaai_ojs, (year,))]

    if conf_key == "acl":
        if year >= 2021:
            return [
                (collect_openreview, ("acl", year)),
                (collect_acl_anthology, (year,)),
            ]
        return [(collect_acl_anthology, (year,))]

    # IJCAI main track: proceedings only.
    if conf_key == "ijcai":
        return [(collect_ijcai_proceedings, (year,))]

    return []


def collect(conf_key: str, year: int, source: str = "auto") -> list[Paper]:
    conf_key = conf_key.strip().lower()
    if conf_key not in CONFERENCE_SOURCES:
        logger.error("Unknown conference: %s. Supported: %s", conf_key, ", ".join(CONFERENCE_SOURCES))
        return []

    for collector, args in source_plan(conf_key, year):
        collector_source = collector_source_name(collector)
        if source != "auto" and collector_source != source:
            continue

        logger.info("Trying %s for %s %d ...", collector.__name__, conf_key.upper(), year)
        papers = try_collect(collector, *args)

        if papers:
            logger.info("  -> collected %d papers via %s", len(papers), collector_source)
            return papers

        logger.info("  -> 0 papers, trying next source ...")

    return []


def collector_source_name(fn: Callable) -> str:
    name = fn.__name__
    if name == "collect_openreview":
        return "openreview"
    if "pmlr" in name:
        return "pmlr"
    if "iclr_archive" in name:
        return "iclr_archive"
    if "neurips_proceedings" in name:
        return "neurips_proceedings"
    if "aaai_ojs" in name:
        return "aaai_ojs"
    if "acl_anthology" in name:
        return "acl_anthology"
    if "ijcai_proceedings" in name:
        return "ijcai_proceedings"
    return name
