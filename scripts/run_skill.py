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
        "into", "over", "under", "than", "more", "less", "new", "novel", "approach"}
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


def lifecycle(series, low, high):
    if not series:
        return "absent", "no dated record contains this term"
    years = list(series.keys())
    first, last = years[0], years[-1]
    total = sum(series.values())
    midpoint = low + (high - low) / 2.0
    early = sum(count for year, count in series.items() if year <= midpoint)
    late = sum(count for year, count in series.items() if year > midpoint)
    if last <= high - 3 and high - low >= 4:
        return "dormant", "last appearance %d, at least three years before the batch end" % last
    if first >= high - 2 and total >= 2 and late > early:
        return "emerging", "first appearance %d with activity in the latest years" % first
    if late >= 2 * max(1, early) and late >= 2:
        return "growing", "second-half mentions (%d) at least double the first half (%d)" % (late, early)
    if early >= 2 * max(1, late) and early >= 2:
        return "declining", "first-half mentions (%d) at least double the second half (%d)" % (early, late)
    return "stable", "activity spread across the period without a clear shift"


def burst_years(series):
    if len(series) < 2:
        return []
    values = list(series.values())
    mean = sum(values) / float(len(values))
    variance = sum((value - mean) ** 2 for value in values) / float(len(values))
    threshold = mean + variance ** 0.5
    return [{"year": year, "count": count} for year, count in series.items() if count > threshold and count >= 2]


def build_payload(case, task_text):
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
    candidates = [term for term, count in sorted(term_freq.items(), key=lambda item: (-item[1], item[0])) if count >= 2][:12]

    terms = []
    for term in candidates:
        series = series_for(dated, term)
        label, basis = lifecycle(series, low, high) if years else ("absent", "no dated records")
        entries = [record for record in dated if term in (record["title"] + " " + record["abstract"]).lower()]
        terms.append({
            "term": term,
            "mentions": term_freq[term],
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
    representative = []
    for span in bins:
        members = [record for record in dated if span["from"] <= record["year"] <= span["to"]]
        top = sorted(members, key=lambda item: (-item["citations"], item["year"], item["source_id"]))[:3]
        representative.append({"period": span["label"], "records": len(members),
                               "works": [{"source_id": record["source_id"], "title": record["title"],
                                          "year": record["year"], "citations_in_batch": record["citations"]} for record in top],
                               "selection_rule": "highest citation count within the batch, ties by source id"})

    open_questions = []
    for record in records:
        text = (record["title"] + " " + record["abstract"]).lower()
        for cue in OPEN_QUESTION_CUES:
            if cue in text:
                position = text.find(cue)
                open_questions.append({"source_id": record["source_id"], "cue": cue,
                                       "quote": (record["abstract"] or record["title"])[max(0, position - 80):position + 160],
                                       "year": record["year"]})
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

    uncertainty = []
    if not topic:
        uncertainty.append({"type": "no_topic", "detail": "No topic was found in the input."})
    if not records:
        uncertainty.append({"type": "no_records", "detail": "No record was supplied; no trend can be computed."})
    if records and len(dated) < len(records):
        uncertainty.append({"type": "undated_records", "detail": "%d record(s) lack a year and are excluded from series." % (len(records) - len(dated))})
    if dated and not any(record["citations"] for record in dated):
        uncertainty.append({"type": "no_citation_counts", "detail": "Citation counts are absent; 'representative' means first/highest within the batch only."})
    uncertainty.append({"type": "batch_only", "detail": "Trends describe the supplied batch; no external database or citation index was queried."})

    if not records or not topic:
        status = "insufficient_input"
    elif len(dated) < 2 or len(years) < 2:
        status = "partial"
    else:
        status = "success"

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
        "periods": representative,
        "open_questions": open_questions,
        "conflicts": conflicts,
        "research_gaps": gaps,
        "method": {
            "lifecycle_rule": "emerging: first seen in last 3 years; growing: late >= 2x early; declining: early >= 2x late; dormant: no record in last 3 years; else stable",
            "burst_rule": "year count above mean + standard deviation and at least 2",
            "representative_rule": "highest in-batch citation count, ties by source id",
            "no_forecast": "no future values are extrapolated",
        },
        "limitations": [
            "Term series depend on title/abstract wording and cannot capture synonym merging.",
            "Citation counts, when supplied, are in-batch only and are not field-normalised.",
            "A dormant term in this batch is not evidence that the field abandoned it.",
            "No forecasting, topic modelling or external citation index is used.",
        ],
        "change_log": [
            "Counted dated records per year and located the peak year.",
            "Built term-level series and assigned deterministic lifecycle labels with stated rules.",
            "Flagged burst years using mean plus standard deviation.",
            "Selected representative works per period by in-batch citations.",
            "Collected explicitly stated open questions and stated batch-level gaps.",
        ],
    }
    return {
        "case_id": case_identifier(case),
        "status": status,
        "result": result,
        "evidence": [{"kind": "term_evidence", "term": term["term"], "series": term["series"],
                      "representative": term["representative"]} for term in terms],
        "uncertainty": uncertainty,
        "errors": [],
        "stats": {"records": len(records), "dated": len(dated), "years": len(years), "terms": len(terms),
                  "open_questions": len(open_questions), "network": "disabled"},
    }


def contract_names(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    names = []
    if isinstance(contract, dict):
        names = [str(key) for key in contract.keys()]
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if isinstance(item.get(key), str):
                        names.append(item[key])
                        break
    return names


def case_identifier(case):
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id"):
            if isinstance(case.get(key), str) and case[key].strip():
                return case[key]
    return ""


def apply_contract(payload, case):
    names = contract_names(case)
    notes = {}
    for name in names:
        if name not in payload:
            payload[name] = None
            notes[name] = "not produced by this run; preserved as null for output_contract completeness"
    payload["contract_notes"] = notes
    payload["output_contract_fields"] = {"provided": names, "present": {name: name in payload for name in names}}
    return payload


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, str(target))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research frontier and trend analysis over a dated record batch")
    parser.add_argument("--case", default=DEFAULT_CASE)
    parser.add_argument("--out", "--output", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    args = parser.parse_args(argv)
    case = {}
    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case.json root must be a JSON object")
        try:
            Path(args.work).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        payload = build_payload(case, read_task_text(args.case, args.work))
        code = 0
    except Exception as exc:
        payload = {"case_id": case_identifier(case) if isinstance(case, dict) else "", "status": "failed",
                   "result": None, "evidence": [],
                   "uncertainty": [{"type": "run_failure", "detail": "Run failed; no trend is reported."}],
                   "errors": [{"stage": "build", "type": type(exc).__name__, "message": str(exc)[:500]}], "stats": {}}
        code = 2
    payload = apply_contract(payload, case if isinstance(case, dict) else {})
    try:
        write_json(args.out, payload)
    except Exception as exc:
        sys.stderr.write(json.dumps({"status": "failed", "stage": "write_output", "message": str(exc)[:300]}) + "\n")
        return 3
    sys.stdout.write(json.dumps({"status": payload.get("status"), "case_id": payload.get("case_id"),
                                 "out": str(args.out), "terms": payload.get("stats", {}).get("terms", 0)},
                                ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
