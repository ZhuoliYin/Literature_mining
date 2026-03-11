from __future__ import annotations

import time

import requests
from tqdm import tqdm

from .common import Paper, SHOW_PROGRESS, clean_text, get_json, logger


def openreview_content_value(value):
    if isinstance(value, dict):
        raw = value.get("value")
        return raw if raw is not None else value.get("values")
    return value


def openreview_group_ids(conf_key: str, year: int) -> list[str]:
    # Year-aware mapping based on conference hosting transitions.
    if conf_key == "iclr":
        if year >= 2018:
            return [f"ICLR.cc/{year}/Conference"]
        if year == 2017:
            return ["ICLR.cc/2017/conference"]
        if 2013 <= year <= 2016:
            return [f"ICLR.cc/{year}"]
        return []

    if conf_key == "icml":
        if year >= 2023:
            return [f"ICML.cc/{year}/Conference"]
        return []

    if conf_key == "neurips":
        if year >= 2021:
            return [f"NeurIPS.cc/{year}/Conference"]
        return []

    if conf_key == "aaai":
        if year >= 2025:
            return [f"AAAI.org/{year}/Conference"]
        return []

    if conf_key == "acl":
        if year >= 2024:
            return [
                f"aclweb.org/ACL/{year}/Conference",
                f"aclweb.org/ACL/{year}/ARR_Commitment",
            ]
        if year >= 2021:
            return [f"aclweb.org/ACL/{year}/Conference"]
        return []

    # IJCAI main track is not on OpenReview.
    return []


def openreview_invitations(conf_key: str, year: int, group_id: str) -> list[str]:
    # ICLR has legacy invitation layouts/suffixes.
    if conf_key == "iclr" and year == 2013:
        return [
            "ICLR.cc/2013/-/submission",
            "ICLR.cc/2013/-/blind_submission",
        ]
    if conf_key == "iclr" and year == 2014:
        return [
            "ICLR.cc/2014/-/submission",
            "ICLR.cc/2014/-/submission/conference",
            "ICLR.cc/2014/-/submission/workshop",
            "ICLR.cc/2014/-/blind_submission",
        ]
    if conf_key == "iclr" and year <= 2017:
        return [
            f"{group_id}/-/submission",
            f"{group_id}/-/blind_submission",
            f"{group_id}/-/Submission",
            f"{group_id}/-/Blind_Submission",
            f"{group_id}/-/Submitted",
        ]

    # Modern OpenReview suffix ordering is venue/year specific.
    if conf_key == "iclr" and 2018 <= year <= 2022:
        ordered_suffixes = ["Blind_Submission", "Submission", "Submitted"]
    elif conf_key == "neurips" and 2021 <= year <= 2022:
        ordered_suffixes = ["Blind_Submission", "Submission", "Submitted"]
    else:
        ordered_suffixes = ["Submission", "Blind_Submission", "Submitted"]

    return [f"{group_id}/-/{suffix}" for suffix in ordered_suffixes]


# ── Acceptance filtering ───────────────────────────────────────────────────
#
# OpenReview venue fields use different conventions across years:
#
# Explicit decisions (contain "accept"/"reject"):
#   content.decision = "Accept (Poster)" / "Reject"
#
# Implicit acceptance via venue labels (API v2, 2023+):
#   content.venue = "ICLR 2024 poster"          ← accepted (no "accept" keyword!)
#   content.venue = "ICLR 2024 spotlight"        ← accepted
#   content.venue = "ICLR 2024 oral"             ← accepted
#   content.venue = "ICML 2024 Poster"           ← accepted
#   content.venue = "NeurIPS 2024 poster"        ← accepted
#   content.venue = "Submitted to ICLR 2024"     ← still under review
#   content.venue = "ICLR 2024 Conference Withdrawn Submission"  ← rejected
#   content.venue = "ICLR 2024 Conference Desk Rejected ..."     ← rejected

_VENUE_REJECT_SIGNALS = ("reject", "withdrawn", "desk reject", "desk_reject")
_VENUE_PENDING_SIGNALS = ("submitted to",)


def _venue_indicates_accepted(venue_str: str) -> bool | None:
    """Interpret a venue/venueid string.

    Returns:
        True  – venue positively indicates acceptance (explicit or implicit)
        False – venue indicates rejection / withdrawal
        None  – venue is empty, pending review, or inconclusive
    """
    if not venue_str:
        return None
    low = venue_str.lower()

    # Explicit rejection or withdrawal
    for sig in _VENUE_REJECT_SIGNALS:
        if sig in low:
            return False

    # Still under review / pending ("Submitted to ICLR 2024")
    for sig in _VENUE_PENDING_SIGNALS:
        if sig in low:
            return None

    # Explicit acceptance keyword
    if "accept" in low:
        return True

    # If we reach here the venue is something like "ICLR 2024 poster",
    # "ICLR 2024 spotlight", "ICML 2024 Poster", etc.
    # A non-empty venue that isn't rejected/withdrawn/pending is accepted.
    return True


def is_accepted_v1(content: dict) -> bool:
    decision = content.get("decision", "")
    if isinstance(decision, str) and decision:
        low = decision.lower()
        if "reject" in low or "withdrawn" in low or "desk" in low:
            return False
        return "accept" in low
    return False


def is_accepted_v2(content: dict) -> bool:
    # Check venue / venueid — the primary signal for API v2.
    for field_name in ("venue", "venueid"):
        raw = openreview_content_value(content.get(field_name, ""))
        if not isinstance(raw, str) or not raw:
            continue
        result = _venue_indicates_accepted(raw)
        if result is False:
            return False
        if result is True:
            return True

    # Fall back to decision field
    decision = openreview_content_value(content.get("decision", ""))
    if isinstance(decision, str) and decision:
        low = decision.lower()
        if "reject" in low or "withdrawn" in low or "desk" in low:
            return False
        return "accept" in low

    return False


def _is_explicitly_rejected(note: dict, is_v2: bool) -> bool:
    """True only if the paper has an explicit reject/withdrawn signal."""
    content = note.get("content", {})

    if is_v2:
        for field_name in ("venue", "venueid"):
            raw = openreview_content_value(content.get(field_name, ""))
            if isinstance(raw, str) and raw:
                result = _venue_indicates_accepted(raw)
                if result is False:
                    return True

    decision = openreview_content_value(content.get("decision", ""))
    if isinstance(decision, str) and decision:
        low = decision.lower()
        if "reject" in low or "withdrawn" in low or "desk" in low:
            return True

    details = note.get("details", {})
    direct_replies = details.get("directReplies", []) if isinstance(details, dict) else []
    for reply in direct_replies:
        inv = str(reply.get("invitation", ""))
        inv_low = inv.lower()
        if not any(token in inv_low for token in ("/decision", "/meta_review", "/acceptance", "/acceptance_decision")):
            continue
        reply_content = reply.get("content") or {}
        dec_raw = (
            reply_content.get("decision", "")
            or reply_content.get("recommendation", "")
            or reply_content.get("acceptance", "")
        )
        dec = openreview_content_value(dec_raw)
        if isinstance(dec, str):
            low = dec.lower()
            if "reject" in low or "withdrawn" in low or "desk" in low:
                return True
    return False


def is_openreview_note_accepted(note: dict, is_v2: bool) -> bool:
    content = note.get("content", {})
    if is_v2 and is_accepted_v2(content):
        return True
    if not is_v2 and is_accepted_v1(content):
        return True

    details = note.get("details", {})
    direct_replies = details.get("directReplies", []) if isinstance(details, dict) else []
    for reply in direct_replies:
        invitation = str(reply.get("invitation", ""))
        invitation_low = invitation.lower()
        # Legacy venues use acceptance / acceptance_decision instead of Decision.
        if not any(token in invitation_low for token in ("/decision", "/meta_review", "/acceptance", "/acceptance_decision")):
            continue
        reply_content = reply.get("content") or {}
        # Decision field can be "decision", "recommendation", or "acceptance"
        dec_raw = (
            reply_content.get("decision", "")
            or reply_content.get("recommendation", "")
            or reply_content.get("acceptance", "")
        )
        decision = openreview_content_value(dec_raw)
        if not isinstance(decision, str):
            continue
        low = decision.lower()
        if "reject" in low or "withdrawn" in low or "desk" in low:
            return False
        if "accept" in low:
            return True
    return False


def collect_openreview(
    conf_key: str,
    year: int,
    *,
    include_submissions: bool = False,
) -> list[Paper]:
    conf_upper = conf_key.upper()
    group_ids = openreview_group_ids(conf_key, year)
    logger.info("OpenReview groups for %s %d: %s", conf_upper, year, group_ids or "[]")

    for group_id in group_ids:
        invitations = openreview_invitations(conf_key, year, group_id)
        logger.info("OpenReview invitation candidates for group %s: %s", group_id, invitations)

        papers = _collect_openreview_api(
            conf_upper,
            year,
            invitations,
            group_id,
            base_url="https://api2.openreview.net/notes",
            is_v2=True,
            include_submissions=include_submissions,
        )
        if papers:
            return papers

        # For API v1: first try with directReplies (works for some venues)
        papers = _collect_openreview_api(
            conf_upper,
            year,
            invitations,
            group_id,
            base_url="https://api.openreview.net/notes",
            is_v2=False,
            include_submissions=include_submissions,
        )
        if papers:
            return papers

        # API v1 fallback: directReplies may be empty in paginated REST
        # responses. Fetch Decision notes separately and join them.
        papers = _collect_openreview_v1_with_decisions(
            conf_key,
            conf_upper,
            year,
            invitations,
            group_id,
            include_submissions=include_submissions,
        )
        if papers:
            return papers

    return []


def _discover_v1_invitations(regex_pattern: str) -> list[str]:
    """Use the OpenReview v1 /invitations endpoint to find invitation IDs matching a regex.

    The /invitations endpoint has a `regex` parameter that supports proper regex matching,
    unlike the /notes endpoint's `invitation` parameter which may not support regex
    patterns (especially .* wildcards) reliably for all venues.
    """
    inv_url = "https://api.openreview.net/invitations"
    found: list[str] = []
    try:
        payload = get_json(inv_url, params={
            "regex": regex_pattern,
            "limit": 2000,
        })
        invitations = payload.get("invitations", [])
        for inv in invitations:
            inv_id = inv.get("id", "")
            if inv_id:
                found.append(inv_id)
    except requests.RequestException:
        pass
    return found


def _fetch_v1_decision_notes_by_invitation(invitation_id: str) -> list[dict]:
    """Fetch all notes for a specific (exact) invitation ID from API v1."""
    base_url = "https://api.openreview.net/notes"
    all_notes: list[dict] = []
    limit = 1000
    offset = 0
    while True:
        try:
            payload = get_json(base_url, params={
                "invitation": invitation_id,
                "offset": offset,
                "limit": limit,
            })
        except requests.RequestException:
            break
        notes = payload.get("notes", [])
        if not notes:
            break
        all_notes.extend(notes)
        offset += len(notes)
        if len(notes) < limit:
            break
        time.sleep(0.1)
    return all_notes


def _fetch_v1_decision_map(conf_key: str, year: int, group_id: str) -> dict[str, str]:
    """Fetch all Decision notes for an API v1 venue.

    Returns a dict mapping forum_id -> decision string (e.g. "Accept (Poster)").

    OpenReview changed invitation naming conventions over the years:
      2018+: {group_id}/-/Paper{N}/Decision          (per-paper Decision)
      2017:  {group_id}/-/paper{N}/acceptance         (lowercase, "acceptance")
      2015-16: {group_id}/-/paper{N}/Acceptance       (mixed case variants)
      2013-14: Various non-standard patterns

    Strategy:
      1. Use the /invitations endpoint (which supports regex via its `regex` param)
         to discover the actual per-paper invitation IDs.
      2. Then fetch notes using those exact invitation IDs.
      3. Fall back to trying regex patterns directly on /notes (works for some venues).
    """
    base_url = "https://api.openreview.net/notes"
    decision_map: dict[str, str] = {}
    limit = 1000

    # ── Step 1: Discover invitation IDs via the /invitations endpoint ─────
    # Build regex patterns to search for decision-related invitations.
    # The /invitations endpoint's `regex` param supports proper regex.
    invitation_regex_patterns = [
        # Modern per-paper pattern (2018+): Paper{N}/Decision
        f"{group_id}/-/Paper.*/Decision",
        f"{group_id}/-/Paper.*/Acceptance_Decision",
        # Also try Meta_Review (some venues store decisions there)
        f"{group_id}/-/Paper.*/Meta_Review",
        # Legacy per-paper patterns (2015-2017)
        f"{group_id}/-/paper.*/[Dd]ecision",
        f"{group_id}/-/paper.*/[Aa]cceptance",
        f"{group_id}/-/Paper.*/[Aa]cceptance",
    ]

    if conf_key == "iclr" and year <= 2014:
        invitation_regex_patterns.extend([
            f"ICLR.cc/{year}/-/paper.*/[Aa]cceptance",
            f"ICLR.cc/{year}/-/paper.*/[Dd]ecision",
            f"ICLR.cc/{year}/conference/-/paper.*/[Aa]cceptance",
        ])

    discovered_invitations: list[str] = []
    for regex_pat in invitation_regex_patterns:
        found = _discover_v1_invitations(regex_pat)
        if found:
            # Filter to only decision/acceptance/meta_review invitations
            for inv_id in found:
                inv_lower = inv_id.lower()
                if any(kw in inv_lower for kw in ("decision", "acceptance", "meta_review")):
                    if inv_id not in discovered_invitations:
                        discovered_invitations.append(inv_id)
            if discovered_invitations:
                logger.info(
                    "Discovered %d decision-related invitations for %s via regex %s (showing first 3: %s)",
                    len(discovered_invitations), group_id, regex_pat,
                    discovered_invitations[:3],
                )
                break

    # Fetch notes from discovered invitations
    if discovered_invitations:
        # For per-paper invitations (e.g. Paper1/Decision, Paper2/Decision, ...),
        # we can batch them efficiently by using the common prefix pattern on /notes.
        # But since the /notes endpoint may not support regex, we need a workaround.
        #
        # Strategy: find the common invitation prefix and use it, or fetch from
        # each discovered invitation individually (batching by shared prefix).

        # Group invitations by their suffix pattern to find a common invitation
        # prefix we can query with. E.g., all "Paper{N}/Decision" share the same
        # structure. Try querying with the first one — if it returns results,
        # the API likely does support some regex. Otherwise, fall back to
        # querying individual invitations in batches.

        # First try: query with the regex pattern directly on /notes
        # (works on some OpenReview deployments)
        for regex_pat in invitation_regex_patterns:
            if decision_map:
                break
            offset = 0
            while True:
                try:
                    payload = get_json(base_url, params={
                        "invitation": regex_pat,
                        "offset": offset,
                        "limit": limit,
                    })
                except requests.RequestException:
                    break
                notes = payload.get("notes", [])
                if not notes:
                    break
                for note in notes:
                    forum = note.get("forum", "")
                    content = note.get("content", {})
                    decision = (
                        content.get("decision", "")
                        or content.get("acceptance", "")
                        or content.get("recommendation", "")
                        or content.get("title", "")
                    )
                    if forum and isinstance(decision, str) and decision:
                        decision_map[forum] = decision
                offset += len(notes)
                if len(notes) < limit:
                    break
                time.sleep(0.1)
            if decision_map:
                logger.info(
                    "Fetched %d Decision notes for %s via regex on /notes: %s",
                    len(decision_map), group_id, regex_pat,
                )

        # Second try: if regex on /notes didn't work, fetch from individual
        # discovered invitations. This is slower but reliable.
        if not decision_map and discovered_invitations:
            bar = tqdm(
                desc="Fetching decisions by invitation",
                total=len(discovered_invitations),
                unit="inv",
                disable=not SHOW_PROGRESS,
                dynamic_ncols=True,
            )
            for inv_id in discovered_invitations:
                notes = _fetch_v1_decision_notes_by_invitation(inv_id)
                for note in notes:
                    forum = note.get("forum", "")
                    content = note.get("content", {})
                    decision = (
                        content.get("decision", "")
                        or content.get("acceptance", "")
                        or content.get("recommendation", "")
                        or content.get("title", "")
                    )
                    if forum and isinstance(decision, str) and decision:
                        decision_map[forum] = decision
                bar.update(1)
            bar.close()
            if decision_map:
                logger.info(
                    "Fetched %d Decision notes for %s via individual invitations",
                    len(decision_map), group_id,
                )

    # ── Step 2: Legacy fallback — try flat (non-per-paper) invitation patterns ──
    if not decision_map:
        flat_invitations = [
            f"{group_id}/-/Decision",
            f"{group_id}/-/Acceptance_Decision",
            f"{group_id}/-/Acceptance",
            f"{group_id}/-/acceptance",
        ]
        for inv_pattern in flat_invitations:
            notes = _fetch_v1_decision_notes_by_invitation(inv_pattern)
            for note in notes:
                forum = note.get("forum", "")
                content = note.get("content", {})
                decision = (
                    content.get("decision", "")
                    or content.get("acceptance", "")
                    or content.get("recommendation", "")
                    or content.get("title", "")
                )
                if forum and isinstance(decision, str) and decision:
                    decision_map[forum] = decision
            if decision_map:
                logger.info(
                    "Fetched %d Decision notes for %s via flat invitation %s",
                    len(decision_map), group_id, inv_pattern,
                )
                break

    if not decision_map:
        logger.info(
            "Fetched 0 Decision notes for %s (tried %d regex patterns + flat patterns)",
            group_id, len(invitation_regex_patterns),
        )

    return decision_map


def _collect_openreview_v1_with_decisions(
    conf_key: str,
    conf_upper: str,
    year: int,
    invitations: list[str],
    group_id: str,
    include_submissions: bool = False,
) -> list[Paper]:
    """API v1 fallback: fetch submissions and decisions separately, then join."""
    # First, fetch the decision map
    decision_map = _fetch_v1_decision_map(conf_key, year, group_id)
    if not decision_map and not include_submissions:
        return []  # No decisions found, can't filter

    # Now fetch all submissions (without relying on directReplies)
    base_url = "https://api.openreview.net/notes"
    seen_forums: set[str] = set()
    papers: list[Paper] = []
    total_fetched = 0
    total_filtered = 0

    for invitation in invitations:
        offset = 0
        found_any = False
        bar = tqdm(
            desc=f"OpenReview v1+decisions {invitation.split('/')[-1]}",
            unit="note",
            disable=not SHOW_PROGRESS,
            dynamic_ncols=True,
        )
        while True:
            try:
                payload = get_json(base_url, params={
                    "invitation": invitation,
                    "offset": offset,
                    "limit": 1000,
                })
            except requests.RequestException:
                break

            notes = payload.get("notes", [])
            if not notes:
                break

            found_any = True
            for note in notes:
                forum = note.get("forum") or note.get("id", "")
                if forum in seen_forums:
                    continue
                seen_forums.add(forum)
                total_fetched += 1

                # Check acceptance using the separately-fetched decision map
                decision = decision_map.get(forum, "")
                if include_submissions:
                    if decision:
                        low = decision.lower()
                        if "reject" in low or "withdrawn" in low or "desk" in low:
                            total_filtered += 1
                            continue
                else:
                    if not decision:
                        total_filtered += 1
                        continue
                    low = decision.lower()
                    if "reject" in low or "withdrawn" in low or "desk" in low:
                        total_filtered += 1
                        continue
                    # Accept if it contains "accept", or if it's a positive
                    # track label like "Oral", "Poster", "Spotlight", "Talk"
                    positive_signals = ("accept", "oral", "poster", "spotlight", "talk")
                    if not any(sig in low for sig in positive_signals):
                        total_filtered += 1
                        continue

                content = note.get("content", {})
                title = clean_text(openreview_content_value(content.get("title")))
                abstract = clean_text(openreview_content_value(content.get("abstract")))

                authors_raw = openreview_content_value(content.get("authors"))
                authors = (
                    [clean_text(a) for a in authors_raw if isinstance(a, str) and clean_text(a)]
                    if isinstance(authors_raw, list)
                    else []
                )

                pdf = openreview_content_value(content.get("pdf"))
                if not pdf:
                    pdf = note.get("pdf")
                if pdf and isinstance(pdf, str) and pdf.startswith("/"):
                    pdf = f"https://openreview.net{pdf}"
                if not pdf and forum:
                    pdf = f"https://openreview.net/pdf?id={forum}"

                paper_url = f"https://openreview.net/forum?id={forum}" if forum else ""

                papers.append(
                    Paper(
                        conference=conf_upper,
                        year=year,
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        paper_url=paper_url,
                        pdf_url=pdf if isinstance(pdf, str) else None,
                        source="openreview",
                    )
                )

            bar.update(len(notes))
            offset += len(notes)
            time.sleep(0.15)

        bar.close()
        if found_any:
            break

    if total_fetched > 0 and not papers:
        logger.warning(
            "v1+decisions: Fetched %d notes, %d decisions, but 0 accepted "
            "(filtered out %d).",
            total_fetched, len(decision_map), total_filtered,
        )

    return papers


def _collect_openreview_api(
    conf_upper: str,
    year: int,
    invitations: list[str],
    group_id: str,
    base_url: str,
    is_v2: bool,
    include_submissions: bool = False,
) -> list[Paper]:
    limit = 1000
    seen_forums: set[str] = set()
    papers: list[Paper] = []
    total_fetched = 0
    total_filtered = 0

    for invitation in invitations:
        logger.info(
            "OpenReview request base=%s invitation=%s venueid=%s",
            base_url,
            invitation,
            group_id if is_v2 else "<none>",
        )
        offset = 0
        found_any = False
        bar = tqdm(
            desc=f"OpenReview {invitation.split('/')[-1]}",
            unit="note",
            disable=not SHOW_PROGRESS,
            dynamic_ncols=True,
        )
        while True:
            params: dict = {
                "invitation": invitation,
                "offset": offset,
                "limit": limit,
                "details": "directReplies",
            }
            if is_v2:
                params["content.venueid"] = group_id

            try:
                payload = get_json(base_url, params=params)
            except requests.RequestException:
                break

            notes = payload.get("notes", [])
            if not notes:
                break

            found_any = True
            for note in notes:
                forum = note.get("forum") or note.get("id", "")
                if forum in seen_forums:
                    continue
                seen_forums.add(forum)
                total_fetched += 1

                # ── Filtering logic ────────────────────────────────
                if include_submissions:
                    if _is_explicitly_rejected(note, is_v2=is_v2):
                        total_filtered += 1
                        continue
                else:
                    if not is_openreview_note_accepted(note, is_v2=is_v2):
                        total_filtered += 1
                        continue

                content = note.get("content", {})
                title = clean_text(openreview_content_value(content.get("title")))
                abstract = clean_text(openreview_content_value(content.get("abstract")))

                authors_raw = openreview_content_value(content.get("authors"))
                authors = (
                    [clean_text(a) for a in authors_raw if isinstance(a, str) and clean_text(a)]
                    if isinstance(authors_raw, list)
                    else []
                )

                pdf = openreview_content_value(content.get("pdf"))
                if not pdf:
                    pdf = note.get("pdf")
                if pdf and isinstance(pdf, str) and pdf.startswith("/"):
                    pdf = f"https://openreview.net{pdf}"
                if not pdf and forum:
                    pdf = f"https://openreview.net/pdf?id={forum}"

                paper_url = f"https://openreview.net/forum?id={forum}" if forum else ""

                papers.append(
                    Paper(
                        conference=conf_upper,
                        year=year,
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        paper_url=paper_url,
                        pdf_url=pdf if isinstance(pdf, str) else None,
                        source="openreview",
                    )
                )

            bar.update(len(notes))
            offset += len(notes)
            time.sleep(0.15)

        bar.close()
        if found_any:
            break

    if total_fetched > 0 and not papers:
        logger.warning(
            "Fetched %d notes but 0 passed the acceptance filter "
            "(filtered out %d). Decisions may not be released yet. "
            "Use --include-submissions to collect all non-rejected submissions.",
            total_fetched,
            total_filtered,
        )

    return papers
