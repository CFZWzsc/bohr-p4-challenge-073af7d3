#!/usr/bin/env python3
"""Research-frontier and trend analysis skill (Python standard library only).

Reads a case file (default /input/case.json) with a topic and a dated batch of
records. It reports yearly output, term-level activity series, a deterministic
lifecycle label per term (emerging / growing / stable / declining / dormant),
burst years, representative work per period, repeatedly-raised open questions
and coverage limits. All statements are bounded to the supplied batch; a term
that is absent is never reported as a research gap in the field.

No network access, no randomness, no private paths.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
RECORD_KEYS = ("records", "papers", "documents", "literature", "sources", "items")
STOP = {"the", "and", "for", "with", "from", "that", "this", "these", "were", "was", "are", "has", "have",
        "study", "studies", "paper", "review", "research", "results", "using", "used", "based", "effect",
        "effects", "group", "data", "analysis", "findings", "however", "also", "can", "may", "not", "but",
        "into", "over", "under", "than", "more", "less", "new", "novel", "approach",
        "cell", "cells", "primary", "cohort", "cohorts", "learning", "patients", "patient", "samples", "sample",
        "therapy", "therapies", "treatment", "treatments", "clinical", "disease", "outcomes", "outcome"}
OPEN_QUESTION_CUES = ("future research", "remains unclear", "remain unclear", "further study", "further research",
                      "not well understood", "limited evidence", "needs further", "open question", "尚未", "仍需",
                      "有待", "尚不明确", "未来研究")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_task_text(case_path, work_dir):
    for path in (Path(case_path).resolve().parent / "task.md", Path("/input/task.md"), Path(work_dir) / "task.md"):
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return ""


def norm_space(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def pick(mapping, names):
    if not isinstance(mapping, dict):
        return None
    for name in names:
        value = mapping.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return norm_space(value)
    if isinstance(value, list):
        return norm_space(" ".join(as_text(item) for item in value))
    if isinstance(value, dict):
        return norm_space(" ".join(as_text(item) for item in value.values()))
    return norm_space(str(value))


def parse_year(value):
    if isinstance(value, int):
        return value if 1800 <= value <= 2100 else None
    match = re.search(r"(1[89]\d{2}|20\d{2})", as_text(value))
    return int(match.group(1)) if match else None


def parse_int(value):
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", as_text(value))
    return int(match.group(0)) if match else 0


def tokenize(text, limit=30):
    lowered = norm_space(text).lower()
    terms = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", lowered) if word not in STOP and not word.isdigit()]
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for index in range(len(chunk) - 1):
            terms.append(chunk[index:index + 2])
    seen, ordered = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered[:limit]


def looks_like_record(node):
    return isinstance(node, dict) and bool({str(k).lower() for k in node.keys()} & {"title", "abstract", "year", "doi", "authors"})


def find_records(case):
    if not isinstance(case, dict):
        return []
    for key in RECORD_KEYS:
        value = case.get(key)
        if isinstance(value, list) and value and any(looks_like_record(item) for item in value):
            return [("/" + key + "/" + str(i), item) for i, item in enumerate(value) if isinstance(item, dict)]
    found = []

    def walk(node, path, depth):
        if depth > 7 or len(found) > 2000:
            return
        if isinstance(node, dict):
            if looks_like_record(node):
                found.append((path, node))
                return
            for key, value in node.items():
                walk(value, path + "/" + str(key), depth + 1)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + "/" + str(index), depth + 1)

    walk(case, "", 0)
    return found


def normalize(raw, locator, index):
    return {
        "source_id": as_text(pick(raw, ("source_id", "record_id", "paper_id", "id"))) or ("F%02d" % (index + 1)),
        "locator": locator,
        "title": as_text(pick(raw, ("title", "name"))),
        "abstract": as_text(pick(raw, ("abstract", "summary"))),
        "year": parse_year(pick(raw, ("year", "publication_year", "date", "published"))),
        "citations": parse_int(pick(raw, ("citations", "citation_count", "cited_by", "cited_by_count"))),
        "venue": as_text(pick(raw, ("venue", "journal", "conference"))),
        "doi": as_text(pick(raw, ("doi", "DOI"))),
        "authors": as_text(pick(raw, ("authors", "author"))),
    }


def topic_of(case, task_text):
    topic = as_text(pick(case, ("topic", "research_topic", "question", "field", "domain", "objective")))
    if not topic:
        for line in task_text.splitlines():
            line = norm_space(line)
            if len(line) > 10 and not line.startswith("#"):
                topic = line
                break
    return topic


def period_bins(years):
    if not years:
        return []
    low, high = min(years), max(years)
    if low == high:
        return [{"label": str(low), "from": low, "to": high}]
    span = high - low + 1
    size = max(1, span // 3)
    bins = []
    start = low
    while start <= high:
        end = min(start + size - 1, high)
        bins.append({"label": "%d-%d" % (start, end), "from": start, "to": end})
        start = end + 1
    return bins[:4]


def series_for(records, term):
    series = {}
    for record in records:
        text = (record["title"] + " " + record["abstract"]).lower()
        if record["year"] and term in text:
            series[record["year"]] = series.get(record["year"], 0) + 1
    return dict(sorted(series.items()))


def lifecycle(series, low, high, dormant_gap=3, growth_factor=2.0, half_counts=None, min_half=3):
    if not series:
        return "absent", "no dated record contains this term"
    years = list(series.keys())
    first, last = years[0], years[-1]
    total = sum(series.values())
    midpoint = low + (high - low) / 2.0
    early = sum(count for year, count in series.items() if year <= midpoint)
    late = sum(count for year, count in series.items() if year > midpoint)
    early_records, late_records = half_counts if half_counts else (None, None)
    if last <= high - dormant_gap and high - low >= 4:
        return "dormant", "last appearance %d, at least %d years before the batch end" % (last, dormant_gap)
    if first >= high - (dormant_gap - 1) and total >= 2 and late > early:
        return "emerging", "first appearance %d with activity in the latest years" % first
    if late >= growth_factor * max(1, early) and late >= 2:
        if early_records is None or late_records is None or min(early_records, late_records) >= min_half:
            return "growing", "second-half mentions (%d) at least %.0fx the first half (%d)" % (late, growth_factor, early)
        return ("insufficient_data",
                "second-half mentions (%d) exceed the first half (%d), but a half-window holds fewer than %d dated "
                "records (early %s, late %s), so a shift cannot be separated from discrete fluctuation"
                % (late, early, min_half, early_records, late_records))
    if early >= growth_factor * max(1, late) and early >= 2:
        if late >= 2 and (early_records is None or late_records is None
                          or min(early_records, late_records) >= min_half):
            return "declining", "first-half mentions (%d) at least %.0fx the second half (%d)" % (early, growth_factor, late)
        return ("insufficient_data",
                "first-half mentions (%d) exceed the second half (%d), but the late half holds only %d mention(s) "
                "across %s dated record(s), so a decline cannot be separated from discrete fluctuation"
                % (early, late, late, late_records))
    return "stable", "activity spread across the period without a clear shift"


def burst_years(series):
    if len(series) < 2:
        return []
    values = list(series.values())
    mean = sum(values) / float(len(values))
    variance = sum((value - mean) ** 2 for value in values) / float(len(values))
    threshold = mean + variance ** 0.5
    return [{"year": year, "count": count} for year, count in series.items() if count > threshold and count >= 2]


import hashlib
from difflib import get_close_matches

sys.dont_write_bytecode = True

STAGE_BY_LIFECYCLE = {"emerging": "appear", "growing": "grow", "stable": "stable",
                      "declining": "decline", "dormant": "dormant", "absent": "absent",
                      "insufficient_data": "not_determinable"}


def load_policy():
    path = Path(__file__).resolve().parent.parent / "assets" / "policy.json"
    try:
        data = load_json(path)
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def pol(policy, dotted, fallback):
    node = policy
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return fallback
    return node


def excerpt(text, limit):
    text = norm_space(text)
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    space = cut.rfind(" ")
    if space >= int(limit * 0.6):
        cut = cut[:space]
    return cut.rstrip(" ,;"), True


def text_of(record):
    return record["abstract"] or record["title"]


def clean_window(text, start, end):
    """Snap a slice to word and sentence boundaries so quotes never start or end mid-word."""
    text = norm_space(text)
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    while start > 0 and text[start - 1] not in " .;:!?":
        start -= 1
    while end < len(text) and text[end] not in " .;:!?":
        end += 1
    if end < len(text) and text[end] in ".;!?":
        end += 1
    return text[start:end].strip()


def build_manifest(root, limit, hash_bytes):
    rows = []
    if root is None:
        return rows
    root = Path(root)
    try:
        if not root.exists():
            return rows
    except OSError:
        return rows
    if root.is_file():
        candidates = [root]
    else:
        candidates = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: item.as_posix())
    for path in candidates:
        if len(rows) >= limit:
            break
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            size = path.stat().st_size
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                remaining = hash_bytes
                while remaining > 0:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
        except OSError:
            continue
        relative = path.name if root.is_file() else path.relative_to(root).as_posix()
        rows.append({"path": relative, "bytes": size, "sha256": digest.hexdigest(),
                     "hash_scope": "full" if size <= hash_bytes else "first_bytes"})
    return rows


def retrieval_scope(topic, terms, records, dated, years, task_text):
    return {
        "query": topic or " ".join(term["term"] for term in terms[:8]),
        "query_basis": "topic text plus the highest-frequency terms in the batch; no search engine or network call is used",
        "inclusion": "records supplied in the case file that carry a title, abstract or DOI; nested record objects are found recursively",
        "exclusion": [
            "undated records are excluded from year series, lifecycle labels and period selection, but kept for open-question extraction",
            "a term needs at least two dated mentions to define a series",
        ],
        "batch_size": len(records),
        "dated_batch_size": len(dated),
        "year_range": [years[0], years[-1]] if years else "no dated record",
        "screened_out": {"undated": len(records) - len(dated)},
        "external_search": False,
        "task_text_used": bool(task_text),
    }


def load_lexicon():
    path = Path(__file__).resolve().parent.parent / "assets" / "theme-lexicon.json"
    try:
        data = load_json(path)
    except (OSError, ValueError):
        data = {}
    concepts = data.get("concepts") if isinstance(data, dict) else None
    return concepts if isinstance(concepts, dict) else {}


def concept_of(term, concepts):
    lowered = str(term).lower()
    for concept in sorted(concepts):
        data = concepts[concept] if isinstance(concepts[concept], dict) else {}
        variants = [concept.lower()] + [str(item).lower() for item in data.get("terms") or []]
        if lowered in variants:
            return concept
    return None


def theme_evolution(terms, limit, concepts=None):
    concepts = concepts or {}
    groups = {}
    order = []
    for term in terms[:limit]:
        concept = concept_of(term["term"], concepts)
        key = concept or ("term:" + term["term"])
        if key not in groups:
            groups[key] = {"concept": concept, "members": []}
            order.append(key)
        groups[key]["members"].append(term)
    rows = []
    for key in order:
        group = groups[key]
        members = group["members"]
        anchor = sorted(members, key=lambda item: (-item["mentions"], item["term"]))[0]
        series = {}
        for member in members:
            for year, count in member["series"].items():
                series[year] = series.get(year, 0) + count
        row = {
            "theme": group["concept"] or anchor["term"],
            "concept": group["concept"],
            "member_terms": [member["term"] for member in members],
            "merged_synonyms": len(members) > 1,
            "stage": STAGE_BY_LIFECYCLE.get(anchor["lifecycle"], "stable"),
            "lifecycle_label": anchor["lifecycle"],
            "from_year": anchor["first_year"],
            "to_year": anchor["last_year"],
            "series": dict(sorted(series.items())),
            "basis": anchor["basis"],
            "source_ids": [work["source_id"] for member in members for work in member["representative"]][:5],
            "merge_split": ("synonyms_merged" if len(members) > 1 else "no_synonym_in_lexicon"),
            "merge_split_note": ("members were aggregated under one concept using assets/theme-lexicon.json; the "
                                 "concept-level series is the sum of the member term series" if len(members) > 1
                                 else "no lexicon synonym was found; the term is reported on its own"),
        }
        rows.append(row)
    if rows:
        return rows
    return [{"theme": "no term meets the two-mention threshold",
             "concept": None, "member_terms": [], "merged_synonyms": False,
             "stage": "not_determinable", "lifecycle_label": "absent",
             "from_year": None, "to_year": None, "series": {},
             "basis": "term series require at least two dated mentions",
             "source_ids": [], "merge_split": "not_detectable_from_term_counts",
             "merge_split_note": "no term could be tracked"}]


def cooccurrence(dated, terms, years):
    if len(terms) < 2 or not years:
        return [{"terms": "fewer than two trackable terms", "label": "not_determinable",
                 "note": "co-occurrence needs at least two terms with two or more dated mentions"}]
    midpoint = (years[0] + years[-1]) / 2.0
    rows = []
    for index in range(len(terms)):
        for other in range(index + 1, len(terms)):
            first, second = terms[index]["term"], terms[other]["term"]
            joined = []
            for record in dated:
                blob = (record["title"] + " " + record["abstract"]).lower()
                if first in blob and second in blob:
                    joined.append(record)
            if len(joined) < 2:
                continue
            early = len([record for record in joined if record["year"] <= midpoint])
            late = len(joined) - early
            if late and not early:
                label = "candidate_merge"
            elif early and not late:
                label = "candidate_split"
            else:
                label = "persistent_cooccurrence"
            rows.append({"terms": [first, second], "records": len(joined), "early_half": early,
                         "late_half": late, "label": label,
                         "source_ids": [record["source_id"] for record in joined][:5],
                         "note": "label is a co-occurrence candidate, not a confirmed merge or split"})
    rows.sort(key=lambda item: (-item["records"], item["terms"][0], item["terms"][1]))
    candidates = [row for row in rows if row["label"] in ("candidate_merge", "candidate_split")]
    persistent = [row for row in rows if row["label"] == "persistent_cooccurrence"]
    selected = (candidates + persistent)[:8]
    return selected or [{"terms": "no term pair co-occurs in two or more dated records",
                         "label": "none_detected",
                         "note": "co-occurrence was checked across every tracked pair"}]


def claim_evidence(topic, records, dated, terms, periods, open_questions, gaps, years, quote_limit):
    claims = []

    def add(category, claim, record, period, source_ids=None, aggregate=False, table_ref=None):
        quote, truncated = ("", False)
        locator = "/"
        source_ids = list(source_ids or [])
        if aggregate:
            claims.append({"category": category, "claim": claim, "source_ids": source_ids,
                           "locator": None, "quote": None, "quote_verified": None,
                           "truncated": False, "period": period, "aggregate": True,
                           "table_ref": table_ref or "result.claim_evidence"})
            return
        if record is not None:
            quote, truncated = excerpt(text_of(record), quote_limit)
            locator = record["locator"]
        claims.append({"category": category, "claim": claim, "source_ids": source_ids,
                       "locator": locator, "quote": quote,
                       "quote_verified": bool(record is not None and quote in text_of(record)),
                       "truncated": truncated, "period": period, "aggregate": False,
                       "table_ref": table_ref})

    if years:
        peak = max(years, key=lambda year: (len([record for record in dated if record["year"] == year]), year))
        peak_records = [record for record in dated if record["year"] == peak]
        add("trend", "the dated batch covers %d-%d with %d records; the peak year is %d with %d record(s)"
            % (years[0], years[-1], len(dated), peak, len(peak_records)),
            None, "%d-%d" % (years[0], years[-1]),
            [record["source_id"] for record in dated], aggregate=True,
            table_ref="result.trend_overview.year_counts")
        midpoint = (years[0] + years[-1]) / 2.0
        early = len([record for record in dated if record["year"] <= midpoint])
        late = len(dated) - early
        direction = "rose" if late > early else ("fell" if late < early else "held")
        add("trend", "batch output %s between the two halves of the window (%d -> %d dated records)"
            % (direction, early, late), None, "%d-%d" % (years[0], years[-1]),
            [record["source_id"] for record in dated], aggregate=True,
            table_ref="result.trend_overview.year_counts")
    for term in terms:
        if term["lifecycle"] in ("emerging", "growing", "declining", "dormant") and term["representative"]:
            work = term["representative"][0]
            add("evolution", "'%s' is %s in this batch (%s)" % (term["term"], term["lifecycle"], term["basis"]),
                None, "%s-%s" % (term["first_year"], term["last_year"]),
                [item["source_id"] for item in term["representative"]], aggregate=True,
                table_ref="result.terms.%s.series" % term["term"])
    for period in periods:
        if period["works"]:
            top = period["works"][0]
            record = None
            for candidate in dated:
                if candidate["source_id"] == top["source_id"]:
                    record = candidate
                    break
            add("representative", "%s is represented by %s (%d in-batch citations)"
                % (period["period"], top["source_id"], top["citations_in_batch"]),
                record, period["period"], [work["source_id"] for work in period["works"]])
    for question in open_questions[:5]:
        record = None
        for candidate in records:
            if candidate["source_id"] == question["source_id"]:
                record = candidate
                break
        add("gap", "a supplied record raises an open question via '%s'" % question["cue"],
            record, "%s" % (record["year"] if record and record["year"] else "undated"), [question["source_id"]])
    for index, gap in enumerate(gaps[:3]):
        anchor = dated[-1] if dated else None
        add("gap", gap["basis"], None, "%d-%d" % (years[0], years[-1]) if years else "no dated period",
            [anchor["source_id"]] if anchor else [], aggregate=True,
            table_ref="result.research_gaps.%d" % index)
    if not claims:
        claims.append({"category": "trend", "claim": "no dated claim can be made from this batch",
                       "source_ids": [], "locator": "/", "quote": "", "quote_verified": False,
                       "truncated": False, "period": "not_applicable"})
    return claims


def representative_selection(bins, terms, dated):
    rows = []
    for span in bins:
        members = [record for record in dated if span["from"] <= record["year"] <= span["to"]]
        stages = []
        for term in terms:
            if any(span["from"] <= year <= span["to"] for year in term["series"]):
                stages.append(term["lifecycle"])
        ranked = sorted(members, key=lambda item: (-item["citations"], item["year"], item["source_id"]))
        chosen = ranked[0] if ranked else None
        if chosen is None:
            representative = None
            reason = "no dated record falls in this period"
        else:
            if chosen["citations"]:
                reason = "highest in-batch citation count (%s) among %d dated record(s) in this period" % (
                    chosen["citations"], len(members))
            else:
                reason = ("no citation counts are supplied, so the earliest record by year then source id is the "
                          "in-batch anchor among %d dated record(s)" % len(members))
            representative = {"source_id": chosen["source_id"], "title": chosen["title"], "year": chosen["year"],
                              "citations_in_batch": chosen["citations"], "locator": chosen["locator"],
                              "reason": reason}
        rows.append({
            "period": span["label"],
            "records_in_period": len(members),
            "representative_source_id": representative["source_id"] if representative else None,
            "representative": representative,
            "rule": "exactly one representative per period: highest in-batch citation count; ties by year then source id; records without citations rank after cited records",
            "covered_stages": sorted(set(stages)) if stages else "no term series in this period",
            "covered_sources": [record["source_id"] for record in ranked[:3]],
            "known_omissions": "undated records and terms mentioned only once are not represented",
        })
    if rows:
        return rows
    return [{"period": "no dated period", "records_in_period": 0, "representative_source_id": None,
             "representative": None, "rule": "not_applicable",
             "covered_stages": "not_applicable", "covered_sources": [],
             "known_omissions": "no record carries a publication year"}]


def gap_exclusion(gaps, dated, terms, years):
    scope = {
        "records_checked": len(dated),
        "year_range": [years[0], years[-1]] if years else "no dated record",
        "terms_checked": [term["term"] for term in terms][:12],
    }
    rows = []
    for gap in gaps:
        evidence = []
        if gap["type"] == "dormant_terms":
            for term in terms:
                if term["lifecycle"] == "dormant" and term["representative"]:
                    work = term["representative"][0]
                    evidence.append({"source_id": work["source_id"], "locator": work["locator"],
                                     "year": work["year"],
                                     "why": "last mention of '%s' in this batch is %s" % (term["term"], term["last_year"])})
        elif gap["type"] == "single_year_batch" and dated:
            evidence.append({"source_id": dated[0]["source_id"], "locator": dated[0]["locator"],
                             "year": dated[0]["year"], "why": "every dated record falls in %d" % years[0]})
        elif gap["type"] == "thin_term_signal":
            for record in dated[:3]:
                evidence.append({"source_id": record["source_id"], "locator": record["locator"],
                                 "year": record["year"],
                                 "why": "only %d term(s) reach two dated mentions" % len(terms)})
        elif dated:
            record = dated[-1]
            evidence.append({"source_id": record["source_id"], "locator": record["locator"],
                             "year": record["year"], "why": gap["basis"]})
        rows.append({
            "gap": gap["type"],
            "basis": gap["basis"],
            "search_scope": scope,
            "exclusion_evidence": evidence if evidence else "no dated record was available for an exclusion check",
            "status": "batch_bounded",
            "external_check_required": True,
        })
    return rows


def needs_human_confirmation(records, dated, terms, years, open_questions):
    items = []
    undated = [record for record in records if not record["year"]]
    if undated:
        items.append({"item": "assign publication years to %d undated record(s)" % len(undated),
                      "locator": undated[0]["locator"],
                      "reason": "undated records are excluded from every year series and lifecycle label"})
    if not dated:
        items.append({"item": "supply records with publication years", "locator": "/",
                      "reason": "no trend, period or lifecycle statement is possible without dated records"})
    if years and len(years) < 3:
        items.append({"item": "extend the batch beyond %d distinct year(s)" % len(years),
                      "locator": "/",
                      "reason": "lifecycle labels need at least three distinct years to separate growth from noise"})
    if terms:
        anchor = terms[0]["representative"][0]["locator"] if terms[0]["representative"] else "/"
        items.append({"item": "confirm whether '%s' was renamed, split or merged with another term" % terms[0]["term"],
                      "locator": anchor,
                      "reason": "term-count series cannot distinguish a renamed topic from a new one"})
    for question in open_questions[:3]:
        items.append({"item": "read the full text behind the cue '%s'" % question["cue"],
                      "locator": question.get("locator", "/"),
                      "reason": "the open question is stated in the abstract; its scope needs the full text"})
    if dated and not any(record["citations"] for record in dated):
        items.append({"item": "supply citation counts", "locator": dated[0]["locator"],
                      "reason": "representative selection falls back to recency and source id"})
    items.append({"item": "check the batch against an external index before any field-level claim",
                  "locator": "/",
                  "reason": "every trend here is bounded by the supplied batch"})
    return items


def build_evidence(terms, dated, quote_limit):
    rows = []
    covered = set()
    by_id = {}
    for record in dated:
        by_id[record["source_id"]] = record
    for term in terms:
        for work in term["representative"][:1]:
            record = by_id.get(work["source_id"])
            if record is None:
                continue
            source = text_of(record)
            quote, truncated = excerpt(source, quote_limit)
            covered.add(record["source_id"])
            rows.append({"kind": "term_evidence", "term": term["term"], "source_id": record["source_id"],
                         "locator": record["locator"], "year": record["year"], "quote": quote,
                         "quote_verified": bool(quote) and quote in source, "truncated": truncated,
                         "series": term["series"], "lifecycle": term["lifecycle"]})
    for record in dated:
        if record["source_id"] in covered:
            continue
        source = text_of(record)
        quote, truncated = excerpt(source, quote_limit)
        rows.append({"kind": "record_evidence", "source_id": record["source_id"], "locator": record["locator"],
                     "year": record["year"], "quote": quote,
                     "quote_verified": bool(quote) and quote in source, "truncated": truncated})
    return rows


def synthesis(topic, records, dated, years, terms, gaps):
    growing = [term["term"] for term in terms if term["lifecycle"] in ("emerging", "growing")]
    declining = [term["term"] for term in terms if term["lifecycle"] in ("declining", "dormant")]
    if not topic or not records:
        direction = "undetermined"
        narrative = "No topic or no record was supplied, so no trend statement is made."
    elif len(years) < 2:
        direction = "undetermined"
        narrative = "All dated records fall in a single year; no direction can be estimated."
    elif growing and declining:
        direction = "mixed"
        narrative = "Some tracked terms expand (%s) while others contract (%s); no single field-level direction is claimed." % (
            ", ".join(growing[:3]), ", ".join(declining[:3]))
    elif growing:
        direction = "expanding"
        narrative = "The batch concentrates recent activity in %s; this is a batch observation, not a field forecast." % ", ".join(growing[:3])
    elif declining:
        direction = "contracting"
        narrative = "Recent batch activity fades for %s; absence here may reflect batch coverage." % ", ".join(declining[:3])
    else:
        direction = "flat_or_unresolved"
        narrative = "Tracked terms show no clear shift within the supplied window."
    caveats = [gap["basis"] for gap in gaps][:3]
    return {
        "narrative": narrative,
        "direction": direction,
        "strongest_signals": [{"term": term["term"], "lifecycle": term["lifecycle"],
                               "mentions": term["mentions"]} for term in terms[:5]],
        "caveats": caveats if caveats else ["no batch-level caveat was triggered"],
        "bounded_by": "supplied batch: %d records, %s" % (
            len(records), "%d-%d" % (years[0], years[-1]) if years else "no dated record"),
        "not_a_forecast": True,
        "decision_scope": "descriptive only; no forecast, funding, hiring or policy decision",
    }


def evidence_matrix(records, quote_limit):
    rows = []
    for record in records:
        source = text_of(record)
        quote, truncated = excerpt(source, quote_limit)
        included = bool(record["year"])
        rows.append({
            "source_id": record["source_id"],
            "locator": record["locator"],
            "title": record["title"],
            "year": record["year"],
            "venue": record["venue"],
            "doi": record["doi"],
            "compared_fields": ["year", "title", "abstract", "citations_in_batch"],
            "included_in_series": included,
            "exclusion_reason": None if included else "no parsable publication year, so the record is excluded from every year series",
            "quote": quote,
            "quote_verified": bool(quote) and quote in source,
            "truncated": truncated,
        })
    return rows


def build_payload(case, task_text, input_root=None):
    policy = load_policy()
    dormant_gap = pol(policy, "lifecycle.dormant_gap_years", 3)
    growth_factor = pol(policy, "lifecycle.growth_factor", 2.0)
    term_limit = pol(policy, "caps.tracked_terms", 12)
    quote_limit = pol(policy, "caps.quote_chars", 240)
    max_claims = pol(policy, "caps.max_claims", 40)

    raw_records = find_records(case)
    records = [normalize(raw, locator, index) for index, (locator, raw) in enumerate(raw_records)]
    topic = topic_of(case, task_text)
    dated = [record for record in records if record["year"]]
    years = sorted({record["year"] for record in dated})
    low = years[0] if years else None
    high = years[-1] if years else None

    year_counts = {}
    for record in dated:
        year_counts[record["year"]] = year_counts.get(record["year"], 0) + 1

    term_freq = {}
    for record in dated:
        for term in set(tokenize(record["title"] + " " + record["abstract"], limit=40)):
            term_freq[term] = term_freq.get(term, 0) + 1
    candidates = [term for term, count in sorted(term_freq.items(), key=lambda item: (-item[1], item[0]))
                  if count >= 2][:term_limit]

    half_early = half_late = 0
    if years:
        midpoint_year = (low + high) / 2.0
        half_early = len([record for record in dated if record["year"] <= midpoint_year])
        half_late = len(dated) - half_early

    terms = []
    for term in candidates:
        series = series_for(dated, term)
        label, basis = lifecycle(series, low, high, dormant_gap, growth_factor,
                                 (half_early, half_late)) if years else ("absent", "no dated records")
        entries = [record for record in dated if term in (record["title"] + " " + record["abstract"]).lower()]
        total_mentions = sum(series.values()) if series else 0
        if total_mentions >= 4 and min(half_early, half_late) >= 3 and label != "insufficient_data":
            confidence = "high"
        elif label == "insufficient_data":
            confidence = "low"
        elif total_mentions >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        terms.append({
            "term": term,
            "mentions": term_freq[term],
            "confidence": confidence,
            "first_year": min(series) if series else None,
            "last_year": max(series) if series else None,
            "series": series,
            "lifecycle": label,
            "basis": basis,
            "bursts": burst_years(series),
            "representative": [
                {"source_id": record["source_id"], "title": record["title"], "year": record["year"],
                 "citations_in_batch": record["citations"], "locator": record["locator"]}
                for record in sorted(entries, key=lambda item: (-item["citations"], item["source_id"]))[:3]
            ],
        })

    bins = period_bins(years)
    representation = representative_selection(bins, terms, dated)
    periods = []
    for index, span in enumerate(bins):
        members = [record for record in dated if span["from"] <= record["year"] <= span["to"]]
        top = sorted(members, key=lambda item: (-item["citations"], item["year"], item["source_id"]))[:3]
        rep = representation[index] if index < len(representation) else {}
        periods.append({"period": span["label"], "records": len(members),
                        "representative": rep.get("representative"),
                        "works": [{"source_id": record["source_id"], "title": record["title"],
                                   "year": record["year"], "citations_in_batch": record["citations"]} for record in top],
                        "selection_rule": "exactly one representative (highest in-batch citations, ties by year then source id); works lists the top three for context only"})

    open_questions = []
    for record in records:
        text = (record["title"] + " " + record["abstract"]).lower()
        for cue in OPEN_QUESTION_CUES:
            if cue in text:
                source = record["abstract"] or record["title"]
                position = text.find(cue)
                window, _truncated = excerpt(clean_window(source, position - 80, position + 160), quote_limit)
                open_questions.append({"source_id": record["source_id"], "locator": record["locator"],
                                       "cue": cue, "quote": window, "year": record["year"],
                                       "quote_verified": bool(window) and window in source})
                break

    gaps = []
    if not dated:
        gaps.append({"type": "no_dated_records", "basis": "no record carries a publication year"})
    elif len(years) < 2:
        gaps.append({"type": "single_year_batch", "basis": "all dated records fall in %d; trends cannot be estimated" % years[0]})
    dormant = [term["term"] for term in terms if term["lifecycle"] == "dormant"]
    if dormant:
        gaps.append({"type": "dormant_terms", "basis": "terms with no recent records in this batch: " + ", ".join(dormant)})
    if len(terms) < 3:
        gaps.append({"type": "thin_term_signal", "basis": "fewer than three terms occur in two or more dated records"})
    gaps.append({"type": "batch_coverage", "basis": "absence here reflects batch coverage, not the absence of a field-wide gap"})

    conflicts = []
    labels = {}
    for term in terms:
        labels.setdefault(term["lifecycle"], []).append(term["term"])
    if "growing" in labels and "declining" in labels:
        conflicts.append({"type": "diverging_term_lifecycles", "growing": labels["growing"], "declining": labels["declining"],
                          "handling": "both movements are reported; no single field-level direction is claimed"})
    pairs = cooccurrence(dated, terms, years)
    merges = [row for row in pairs if row.get("label") == "candidate_merge"]
    splits = [row for row in pairs if row.get("label") == "candidate_split"]
    for row in (merges[:2] + splits[:2])[:3]:
        conflicts.append({"type": row["label"], "terms": row["terms"], "records": row["records"],
                          "handling": "reported as a co-occurrence candidate; it is not a confirmed merge or split"})

    uncertainty = []
    if not topic:
        uncertainty.append({"type": "no_topic", "detail": "No topic was found in the input."})
    if not records:
        uncertainty.append({"type": "no_records", "detail": "No record was supplied; no trend can be computed."})
    if records and len(dated) < len(records):
        uncertainty.append({"type": "undated_records", "detail": "%d record(s) lack a year and are excluded from series." % (len(records) - len(dated))})
    if dated and not any(record["citations"] for record in dated):
        uncertainty.append({"type": "no_citation_counts", "detail": "Citation counts are absent; 'representative' means first/highest within the batch only."})
    if any(term["lifecycle"] == "emerging" for term in terms):
        uncertainty.append({"type": "short_window", "detail": "Emerging labels use a three-year tail and can reflect indexing lag rather than a real shift."})
    uncertainty.append({"type": "batch_only", "detail": "Trends describe the supplied batch; no external database or citation index was queried."})

    if not records or not topic:
        status = "insufficient_input"
    elif len(dated) < 2 or len(years) < 2:
        status = "partial"
    else:
        status = "success"

    claims = claim_evidence(topic, records, dated, terms, periods, open_questions, gaps, years, quote_limit)[:max_claims]

    result = {
        "topic": topic,
        "trend_overview": {
            "records": len(records),
            "dated_records": len(dated),
            "year_range": [low, high],
            "year_counts": dict(sorted(year_counts.items())),
            "peak_year": max(year_counts.items(), key=lambda item: (item[1], item[0]))[0] if year_counts else None,
            "growth_note": "counts are absolute within the batch; no normalisation by database size is possible",
        },
        "terms": terms,
        "periods": periods,
        "open_questions": open_questions,
        "conflicts": conflicts,
        "research_gaps": gaps,
        "evidence_matrix": evidence_matrix(records, quote_limit),
        "retrieval_scope": retrieval_scope(topic, terms, records, dated, years, task_text),
        "theme_evolution": theme_evolution(terms, term_limit, load_lexicon()),
        "cooccurrence": pairs,
        "claim_evidence": claims,
        "representative_selection": representation,
        "gap_exclusion": gap_exclusion(gaps, dated, terms, years),
        "needs_human_confirmation": needs_human_confirmation(records, dated, terms, years, open_questions),
        "synthesis": synthesis(topic, records, dated, years, terms, gaps),
        "method": {
            "lifecycle_rule": "emerging: first seen in the last %d years; growing: late >= %.0fx early; declining: early >= %.0fx late; dormant: no record in the last %d years; else stable"
                             % (dormant_gap - 1, growth_factor, growth_factor, dormant_gap),
            "burst_rule": "year count above mean + standard deviation and at least 2",
            "representative_rule": "highest in-batch citation count, ties by source id; undated records are never selected",
            "evolution_rule": "appear / grow / stable / decline / dormant are measured from the batch; merge and split are reported only as co-occurrence candidates",
            "no_forecast": "no future values are extrapolated",
            "deterministic": True,
            "network": False,
        },
        "limitations": [
            "Term series depend on title/abstract wording and cannot capture synonym merging.",
            "Year fields are used as supplied; online-first, issue and preprint dates are not distinguished.",
            "Citation counts, when supplied, are in-batch only and are not field-normalised.",
            "A dormant term in this batch is not evidence that the field abandoned it.",
            "Merge and split cannot be confirmed from term counts alone.",
            "No forecasting, topic modelling or external citation index is used.",
        ],
        "change_log": [
            "Counted dated records per year and located the peak year.",
            "Built term-level series and assigned deterministic lifecycle labels with stated rules.",
            "Flagged burst years using mean plus standard deviation.",
            "Selected representative works per period by in-batch citations.",
            "Mapped each lifecycle to an evolution stage and reported co-occurrence candidates for merge/split.",
            "Backed each trend, evolution, representative and gap claim with a locator and an exact quote.",
            "Collected explicitly stated open questions and stated batch-level gaps.",
        ],
    }
    return {
        "case_id": case_identifier(case) or "unknown",
        "status": status,
        "result": result,
        "evidence": build_evidence(terms, dated, quote_limit),
        "uncertainty": uncertainty,
        "errors": [],
        "stats": {"records": len(records), "dated": len(dated), "years": len(years), "terms": len(terms),
                  "claims": len(claims), "open_questions": len(open_questions),
                  "human_confirmation_items": len(result["needs_human_confirmation"]),
                  "network": "disabled"},
        "input_manifest": build_manifest(input_root, pol(policy, "caps.max_manifest_files", 200),
                                         pol(policy, "caps.manifest_hash_bytes", 1048576)),
        "run": {"entrypoint": "scripts/sk_entry.py", "network": "disabled", "stdlib_only": True,
                "deterministic": True, "policy_version": pol(policy, "version", "unknown")},
    }


def case_identifier(case):
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id"):
            if isinstance(case.get(key), str) and case[key].strip():
                return case[key]
    return ""


RESERVED_FIELDS = {"case_id", "status", "result", "evidence", "uncertainty", "errors", "stats",
                   "contract_notes", "contract_extras", "output_contract_fields", "input_manifest", "run"}

INTERPRETED_INPUT_KEYS = {"case_id", "caseId", "id", "title", "topic", "research_topic", "question", "field",
                          "domain", "objective", "records", "papers", "documents", "literature", "sources",
                          "items", "filters", "year_range", "output_contract"}

CONTRACT_ALIASES = {
    "summary": "synthesis",
    "report": "synthesis",
    "trend_summary": "trend_overview",
    "overview": "trend_overview",
    "timeline": "periods",
    "representative_works": "periods",
    "themes": "theme_evolution",
    "theme_series": "terms",
    "claims": "claim_evidence",
    "evidence_claims": "claim_evidence",
    "gaps": "research_gaps",
    "gap": "research_gaps",
    "open_question": "open_questions",
    "conflicts": "conflicts",
    "contradictions": "conflicts",
    "questions": "needs_human_confirmation",
    "human_confirmation": "needs_human_confirmation",
    "scope": "retrieval_scope",
    "search_scope": "retrieval_scope",
    "notes": "uncertainty",
    "uncertainties": "uncertainty",
    "method_notes": "method",
    "limits": "limitations",
    "evolution": "theme_evolution",
    "representative": "representative_selection",
}


def contract_entries(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    shape = "absent"
    names = []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            shape = "json_schema"
            names = [str(key) for key in contract["properties"].keys()]
        else:
            shape = "mapping"
            names = [str(key) for key in contract.keys()]
    elif isinstance(contract, list):
        shape = "list"
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if isinstance(item.get(key), str):
                        names.append(item[key])
                        break
    elif isinstance(contract, str):
        shape = "string"
        names = [contract]
    ordered = []
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered, shape


def not_determinable(name, candidates):
    lowered = [candidate.lower() for candidate in candidates]
    close = get_close_matches(str(name).lower(), lowered, n=3, cutoff=0.35)
    mapping = {}
    for candidate in candidates:
        mapping[candidate.lower()] = candidate
    closest = [mapping[item] for item in close] or sorted(candidates)[:3]
    return {
        "status": "not_determinable",
        "produced": False,
        "field": str(name),
        "reason": "No derivation in this skill maps to the declared contract field, and the supplied batch does not contain the data that would decide it.",
        "closest_produced_fields": closest,
        "next_action": "Derive this field from the input materials during review, or keep it explicitly unavailable; do not fabricate a value.",
    }


def apply_contract(payload, case):
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    candidates = [str(key) for key in payload.keys()] + [str(key) for key in result.keys() if key not in payload]
    names, shape = contract_entries(case)
    notes, sources, unknown, aliases = {}, {}, [], {}
    for name in names:
        if name in RESERVED_FIELDS:
            notes[name] = "already produced as a top-level field; kept unchanged"
            sources[name] = "top_level"
            continue
        if name in payload:
            notes[name] = "produced directly by this run"
            sources[name] = "top_level"
            continue
        if name in result:
            payload[name] = result[name]
            notes[name] = "lifted from result.%s so the declared field exists at top level" % name
            sources[name] = "result"
            continue
        target = CONTRACT_ALIASES.get(name.lower())
        if target and target in result:
            payload[name] = result[target]
            notes[name] = "aliased to result.%s" % target
            sources[name] = "alias:%s" % target
            aliases[name] = target
            continue
        if target and target in payload:
            payload[name] = payload[target]
            notes[name] = "aliased to top-level %s" % target
            sources[name] = "alias:%s" % target
            aliases[name] = target
            continue
        payload[name] = not_determinable(name, candidates)
        notes[name] = "no derivation available; a structured not_determinable object was written instead of null"
        sources[name] = "not_determinable"
        unknown.append(name)
    payload["contract_notes"] = notes
    payload["contract_extras"] = {
        "contract_shape": shape,
        "declared_keys": names,
        "not_determinable_keys": unknown,
        "aliases_applied": aliases,
        "uninterpreted_input_keys": sorted(str(key) for key in (case.keys() if isinstance(case, dict) else [])
                                           if str(key) not in INTERPRETED_INPUT_KEYS),
    }
    payload["output_contract_fields"] = {
        "provided": names,
        "present": dict((name, True) for name in names),
        "sources": sources,
        "not_determinable": unknown,
    }
    return payload


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, str(target))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def failed_payload(case, errors):
    return {
        "case_id": (case_identifier(case) if isinstance(case, dict) else "") or "unknown",
        "status": "failed",
        "result": {"trend_overview": {"status": "not_produced",
                                      "reason": "the run failed before any trend could be computed"}},
        "evidence": [],
        "uncertainty": [{"type": "run_failure", "detail": "Run failed; no trend is reported."}],
        "errors": list(errors),
        "stats": {"records": 0, "network": "disabled"},
        "input_manifest": [],
        "run": {"entrypoint": "scripts/sk_entry.py", "network": "disabled", "stdlib_only": True,
                "deterministic": True},
    }


def parse_cli(argv):
    parser = argparse.ArgumentParser(description="Research frontier and trend analysis over a dated record batch")
    parser.add_argument("--input", "--case", dest="input", default=DEFAULT_CASE, help="input directory or case.json")
    parser.add_argument("--work", default=DEFAULT_WORK)
    parser.add_argument("--out", "--output", dest="out", default=DEFAULT_OUT, help="output directory or result.json")
    return parser.parse_args(argv)


def resolve_out(value):
    path = Path(value)
    if path.suffix.lower() == ".json":
        return path.parent, path
    return path, path / "result.json"


def resolve_inputs(value):
    path = Path(value)
    if path.is_dir():
        return path / "case.json", path
    return path, path.parent


def write_artifacts(out_dir, payload):
    """Write a human-readable trend report next to result.json."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if not result:
        return []
    target = Path(out_dir)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    overview = result.get("trend_overview") or {}
    lines = ["# Research frontier and theme evolution", "",
             "Topic: %s | Status: %s" % (result.get("topic") or "not stated", payload.get("status")), "",
             "## 1. Trend overview", "",
             "- Dated records: %s of %s | Year range: %s" % (overview.get("dated_records"), overview.get("records"),
                                                             overview.get("year_range")),
             "- Peak year: %s" % overview.get("peak_year"),
             "- Note: %s" % overview.get("growth_note"), "",
             "| year | records |", "|---|---|"]
    for year, count in sorted((overview.get("year_counts") or {}).items()):
        lines.append("| %s | %s |" % (year, count))
    lines += ["", "## 2. Theme evolution", "",
              "| theme | members | lifecycle | stage | confidence |", "|---|---|---|---|---|"]
    confidence = {}
    for term in result.get("terms") or []:
        confidence[term.get("term")] = term.get("confidence")
    for row in result.get("theme_evolution") or []:
        members = row.get("member_terms") or [row.get("theme")]
        level = confidence.get((row.get("member_terms") or [None])[0]) or "n/a"
        lines.append("| %s | %s | %s | %s | %s |" % (row.get("theme"), ", ".join(members), row.get("lifecycle_label"),
                                                     row.get("stage"), level))
    lines += ["", "## 3. Representative work per period", "",
              "| period | records | representative | year | reason |", "|---|---|---|---|---|"]
    for row in result.get("representative_selection") or []:
        rep = row.get("representative") or {}
        lines.append("| %s | %s | %s | %s | %s |" % (row.get("period"), row.get("records_in_period"),
                                                     rep.get("source_id") or "none", rep.get("year") or "",
                                                     rep.get("reason") or row.get("rule")))
    lines += ["", "## 4. Claims and evidence binding", ""]
    for claim in (result.get("claim_evidence") or [])[:8]:
        anchor = "aggregate table: %s" % claim.get("table_ref") if claim.get("aggregate") else str(claim.get("locator"))
        lines.append("- [%s] %s (%s)" % (claim.get("category"), claim.get("claim"), anchor))
    lines += ["", "## 5. Gaps and open questions", ""]
    for gap in result.get("research_gaps") or []:
        lines.append("- Gap (%s): %s" % (gap.get("type"), gap.get("basis")))
    for question in (result.get("open_questions") or [])[:5]:
        lines.append("- Open question [%s]: %s" % (question.get("source_id"), question.get("quote")))
    report_path = target / "report.md"
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return ["report.md"]


def write_result(out_path, payload, work_dir):
    for target in (Path(out_path), Path(work_dir) / "result.json"):
        try:
            write_json(target, payload)
            return str(target)
        except Exception:
            continue
    return ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out_path = Path(DEFAULT_OUT) / "result.json"
    work_dir = Path(DEFAULT_WORK)
    case = {}
    errors = []
    broken_input = False
    payload = None
    try:
        args = parse_cli(argv)
        work_dir = Path(args.work)
        _out_dir, out_path = resolve_out(args.out)
        case_path, input_root = resolve_inputs(args.input)
        if not case_path.is_file():
            errors.append({"stage": "input", "type": "case_file_missing",
                           "message": "no case.json was found at the resolved input path"})
        else:
            try:
                case = load_json(case_path)
                if not isinstance(case, dict):
                    raise ValueError("case.json root must be a JSON object")
            except Exception as exc:
                case = {}
                broken_input = True
                errors.append({"stage": "input", "type": "case_unreadable", "message": str(exc)[:500]})
        try:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        task_text = read_task_text(str(case_path), str(work_dir))
        payload = build_payload(case, task_text, input_root)
    except BaseException as exc:
        payload = failed_payload(case, [{"stage": "build", "type": type(exc).__name__, "message": str(exc)[:500]}])
    if not isinstance(payload, dict):
        payload = failed_payload(case, [{"stage": "build", "type": "invalid_payload", "message": "payload was not a dict"}])
    if errors:
        payload["errors"] = list(payload.get("errors") or []) + errors
    if broken_input:
        payload["status"] = "failed"
    try:
        payload = apply_contract(payload, case if isinstance(case, dict) else {})
    except BaseException as exc:
        payload["contract_notes"] = {}
        payload["contract_extras"] = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
        payload["output_contract_fields"] = {"provided": [], "present": {}}
    written = write_result(out_path, payload, work_dir)
    try:
        payload["artifacts"] = write_artifacts(Path(out_path).parent, payload)
        if payload["artifacts"]:
            write_result(out_path, payload, work_dir)
    except BaseException as exc:
        payload["artifacts"] = []
        payload["artifact_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
    if not written:
        sys.stderr.write(json.dumps({"status": payload.get("status"), "stage": "write_output",
                                     "message": "result.json could not be written"}, ensure_ascii=False) + "\n")
    summary = {"status": payload.get("status"), "case_id": payload.get("case_id"), "out": written,
               "contract_keys": len((payload.get("output_contract_fields") or {}).get("provided") or [])}
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        try:
            fallback = Path(DEFAULT_OUT) / "result.json"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "w", encoding="utf-8") as handle:
                json.dump({"case_id": "unknown", "status": "failed",
                           "result": {"trend_overview": {"status": "not_produced"}},
                           "evidence": [], "uncertainty": [{"type": "run_failure"}], "errors": [],
                           "stats": {}, "contract_notes": {}}, handle, ensure_ascii=False, indent=2)
        except BaseException:
            pass
    sys.exit(0)
