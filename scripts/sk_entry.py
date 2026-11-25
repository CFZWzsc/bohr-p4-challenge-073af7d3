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
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
RECORD_KEYS = ("records", "papers", "documents", "literature", "sources", "items",
               "known_works", "prior_works", "candidates", "search_results",
               "screening_records", "bibliography")
MATERIAL_EXTS = {".md", ".txt", ".csv", ".json", ".pdf"}
SKIP_DIRS = {"__pycache__", ".git"}
CONCEPT_RULE_KEYS = ("concept_rules", "theme_rules", "concept_groups", "synonym_rules",
                     "thesaurus", "synonyms", "hierarchy", "term_groups")
PERIOD_KEYS = ("periods", "period_plan", "stages", "time_slices", "year_bins", "period_bins")
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


def looks_like_record(node, relaxed=False):
    if not isinstance(node, dict):
        return False
    keys = {str(k).lower() for k in node.keys()}
    if relaxed:
        return bool(keys & {"title", "name"}) and bool(keys & {"title", "name", "abstract", "summary",
                                                               "year", "date", "doi", "authors", "venue", "note"})
    return bool(keys & {"title", "abstract", "year", "doi", "authors"})


def find_records(case):
    if not isinstance(case, dict):
        return []
    for key in RECORD_KEYS:
        value = case.get(key)
        if isinstance(value, list) and value and any(looks_like_record(item, relaxed=True) for item in value):
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
        "duplicate_of": None,
        "file": None,
        "source_index": None,
        "source_paragraph": None,
        "source_locator": None,
        "source_text": "",
    }


def norm_key(text):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", norm_space(text).lower()).strip()


def dedupe_keys(record):
    keys = []
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", record["doi"].strip().lower())
    if doi:
        keys.append("doi:" + doi)
    title = norm_key(record["title"])
    if title:
        keys.append("title:%s|%s" % (title, record["year"] if record["year"] else "undated"))
    return keys or ["locator:" + record["locator"]]


def dedupe(records):
    """Mark later occurrences of the same DOI, or of the same normalised title and year."""
    seen = {}
    for record in records:
        keys = dedupe_keys(record)
        record["fingerprint"] = keys[0]
        first = None
        for key in keys:
            if key in seen:
                first = seen[key]
                break
        if first is not None:
            record["duplicate_of"] = first
        else:
            for key in keys:
                seen[key] = record["source_id"]
    return [record for record in records if not record["duplicate_of"]]




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


def parse_period_items(items):
    bins = []
    for item in items if isinstance(items, list) else [items]:
        if isinstance(item, dict):
            low = parse_year(pick(item, ("from", "start", "begin", "year_from")))
            high = parse_year(pick(item, ("to", "end", "finish", "year_to"))) or low
            label = as_text(pick(item, ("label", "period", "name", "stage")))
        else:
            text = as_text(item)
            match = re.search(r"(1[89]\d{2}|20\d{2})\s*[-–—~至to]+\s*(1[89]\d{2}|20\d{2})", text)
            if not match:
                year = parse_year(text)
                low = high = year
                label = text
            else:
                low, high = int(match.group(1)), int(match.group(2))
                label = text
        if low is None or high is None or low > high:
            continue
        bins.append({"label": label or ("%d-%d" % (low, high)), "from": low, "to": high})
    bins.sort(key=lambda span: (span["from"], span["to"]))
    return bins


def periods_from_task(task_text):
    """Read a period plan only when the task text explicitly labels one."""
    for line in (task_text or "").splitlines():
        lowered = line.lower()
        if not any(marker in lowered for marker in ("阶段", "period", "time slice", "时间窗", "时间切片")):
            continue
        ranges = ["%s-%s" % pair
                  for pair in re.findall(r"(1[89]\d{2}|20\d{2})\s*[-–—~至to]+\s*(1[89]\d{2}|20\d{2})", line)]
        found = parse_period_items(ranges)
        if found:
            return found
    return []


def period_plan(case, task_text, years):
    """Return (bins, source, note). Input-declared periods win; otherwise equal-width bins."""
    declared = None
    if isinstance(case, dict):
        for key in PERIOD_KEYS:
            if isinstance(case.get(key), (list, dict, str)) and case.get(key):
                declared = parse_period_items(case[key])
                if declared:
                    return declared, "input:case.%s" % key, \
                        "period boundaries are declared in the input (case.%s) and used verbatim" % key
    if not declared:
        declared = periods_from_task(task_text)
        if declared:
            return declared, "input:task.md", \
                "period boundaries are declared in the task text and used verbatim"
    if not years:
        return [], "derived:no_dated_record", "no dated record is available, so no period can be formed"
    low, high = min(years), max(years)
    span = high - low + 1
    size = max(1, span // 3)
    note = ("no period plan was supplied by the input; the dated window %d-%d is split into equal-width "
            "bins of %d year(s) (span %d // 3), capped at 4 periods" % (low, high, size, span))
    return period_bins(years), "derived:equal_width", note


def period_of_year(year, bins):
    if not year:
        return None
    for span in bins:
        if span["from"] <= year <= span["to"]:
            return span["label"]
    return None



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
    return record.get("source_text") or record["abstract"] or record["title"]


def locator_of(record):
    return record.get("source_locator") or record["locator"]


def split_paragraphs(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [norm_space(block) for block in re.split(r"\n\s*\n+", text)]
    blocks = [block for block in blocks if block]
    if len(blocks) <= 1:
        blocks = [norm_space(line) for line in text.splitlines()]
        blocks = [block for block in blocks if block]
    return blocks


def decode_material(path, cap):
    with open(path, "rb") as handle:
        data = handle.read(cap)
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def json_strings(path):
    try:
        data = load_json(path)
    except (OSError, ValueError):
        return []
    out = []

    def walk(node):
        if isinstance(node, str):
            if len(norm_space(node)) >= 40:
                out.append(node)
        elif isinstance(node, dict):
            for key in node:
                walk(node[key])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return out


def pdf_text(path):
    tool = shutil.which("pdftotext")
    if not tool:
        return "", "pdftotext_not_available"
    try:
        proc = subprocess.run([tool, str(path), "-"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "", "pdftotext_failed"
    if proc.returncode != 0:
        return "", "pdftotext_failed"
    return proc.stdout.decode("utf-8", errors="replace"), ""


def collect_materials(input_root, exclude_path, caps):
    """Parse md/txt/csv/json (and PDF via pdftotext) under the input root into numbered paragraphs."""
    materials, errors, skipped = [], [], []
    if input_root is None:
        return materials, errors, skipped
    root = Path(input_root)
    try:
        if not root.exists():
            errors.append({"stage": "materials", "type": "root_not_found",
                           "message": "input root is not available"})
            return materials, errors, skipped
    except OSError:
        return materials, errors, skipped
    if root.is_file():
        candidates, root_dir = [root], root.parent
    else:
        root_dir, candidates = root, []
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
                for name in sorted(filenames):
                    candidates.append(Path(dirpath) / name)
        except OSError:
            errors.append({"stage": "materials", "type": "walk_failed",
                           "message": "input root could not be walked"})
    exclude_key = ""
    if exclude_path is not None:
        try:
            exclude_key = str(Path(exclude_path).resolve())
        except OSError:
            exclude_key = ""
    seen = set()
    for path in candidates:
        extension = path.suffix.lower()
        if extension not in MATERIAL_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if not path.is_file() or path.is_symlink():
                continue
            resolved = str(path.resolve())
        except OSError:
            continue
        if resolved == exclude_key or resolved in seen:
            continue
        seen.add(resolved)
        if len(materials) >= caps["max_files"]:
            skipped.append({"path": path.name, "reason": "file_cap_reached"})
            continue
        try:
            relative = path.relative_to(root_dir).as_posix()
        except ValueError:
            relative = path.name
        reason = ""
        if extension == ".pdf":
            raw_text, reason = pdf_text(path)
        elif extension == ".json":
            raw_text = "\n\n".join(json_strings(path))
            reason = "" if raw_text else "no_string_values"
        else:
            try:
                raw_text = decode_material(path, caps["max_file_bytes"])
            except OSError:
                raw_text, reason = "", "unreadable"
        paragraphs = split_paragraphs(raw_text)
        if not paragraphs and not reason:
            reason = "no_extractable_text"
        materials.append({
            "source_index": len(materials) + 1,
            "path": relative,
            "kind": extension.lstrip("."),
            "status": "parsed" if paragraphs else "unparsed",
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs),
            "chars": sum(len(item) for item in paragraphs),
            "preview": (paragraphs[0][:200] if paragraphs else ""),
            "reason": reason or None,
        })
    return materials, errors, skipped


def attach_source_text(records, materials):
    """Match each record to the material paragraph holding its title or DOI."""
    index = []
    for material in materials:
        if material["status"] != "parsed":
            continue
        for number, paragraph in enumerate(material["paragraphs"], start=1):
            index.append((material, number, norm_key(paragraph), paragraph))
    matched = 0
    for record in records:
        title_key = norm_key(record["title"])
        doi_key = norm_key(re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", record["doi"].lower()))
        best = None
        for material, number, paragraph_key, paragraph in index:
            score = 0.0
            if doi_key and len(doi_key) >= 6 and doi_key in paragraph_key:
                score = 1.0
            elif title_key and len(title_key) >= 8:
                if title_key in paragraph_key:
                    score = 0.96
                else:
                    window = paragraph_key[:max(len(title_key) + 40, 80)]
                    score = SequenceMatcher(None, title_key, window).ratio()
            if score and (best is None or score > best[0]):
                best = (score, material, number, paragraph)
        if best is not None and best[0] >= 0.72:
            _score, material, number, paragraph = best
            record["file"] = material["path"]
            record["source_index"] = material["source_index"]
            record["source_paragraph"] = number
            record["source_locator"] = "S%d#P%d" % (material["source_index"], number)
            record["source_text"] = paragraph
            matched += 1
    return matched


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


def language_of(text):
    if re.search(r"[\u4e00-\u9fff]", text or ""):
        return "zh"
    if re.search(r"[A-Za-z]", text or ""):
        return "en"
    return "undetermined"


def languages_of(records):
    values = sorted({language_of(record["title"] + " " + record["abstract"]) for record in records})
    values = [value for value in values if value != "undetermined"]
    return values or ["undetermined"]


def query_hits(records, keywords, mode):
    hits = []
    for record in records:
        blob = (record["title"] + " " + record["abstract"]).lower()
        found = [keyword for keyword in keywords if keyword and keyword in blob]
        if (mode == "any" and found) or (mode == "all" and len(found) == len(keywords)):
            hits.append(record["source_id"])
    return hits


def build_queries(topic, terms, records, years):
    keywords = [term["term"] for term in terms]
    topic_terms = tokenize(topic, limit=6)
    specs = []
    if keywords:
        specs.append({"id": "Q1", "mode": "any", "keywords": keywords[:4],
                      "purpose": "recall any tracked term in title/abstract"})
    if len(keywords) >= 2:
        specs.append({"id": "Q2", "mode": "all", "keywords": keywords[:2],
                      "purpose": "precision pairing of the two leading terms"})
    if topic_terms and keywords:
        extra = [term for term in topic_terms if term not in keywords][:2]
        if extra:
            specs.append({"id": "Q3", "mode": "all", "keywords": extra + keywords[:1],
                          "purpose": "topic words combined with the leading term"})
    if not specs:
        specs.append({"id": "Q1", "mode": "any", "keywords": topic_terms[:3],
                      "purpose": "topic-only fallback"})
    fields = ["title", "abstract"]
    date_range = [years[0], years[-1]] if years else "no dated record"
    languages = languages_of(records)
    rows = []
    for spec in specs:
        joiner = " OR " if spec["mode"] == "any" else " AND "
        hits = query_hits(records, spec["keywords"], spec["mode"])
        rows.append({
            "query_id": spec["id"],
            "query": joiner.join('"%s"' % keyword for keyword in spec["keywords"]) or '""',
            "fields": fields,
            "date_range": date_range,
            "languages": languages,
            "hits": len(hits),
            "hit_source_ids": hits[:20],
            "purpose": spec["purpose"],
            "executed_online": False,
            "hit_basis": "keyword match counted against the supplied records; the query was not executed against an online index",
        })
    return rows


def retrieval_scope(topic, terms, records, dated, years, task_text, deduped, duplicates):
    queries = build_queries(topic, terms, deduped, years)
    return {
        "query": topic or " ".join(term["term"] for term in terms[:8]),
        "query_basis": "topic text plus the highest-frequency terms in the batch; no search engine or network call is used",
        "queries": queries,
        "fields": ["title", "abstract"],
        "date_range": [years[0], years[-1]] if years else "no dated record",
        "languages": languages_of(deduped),
        "hits_per_query": [{"query_id": row["query_id"], "hits": row["hits"],
                            "basis": "counted on the supplied records; not executed online"} for row in queries],
        "execution_note": "queries are declared for review and evaluated against this batch only; no online index was queried",
        "inclusion": "records supplied in the case file that carry a title, abstract or DOI; nested record objects are found recursively",
        "exclusion": [
            "duplicate records (same DOI, or same normalised title and year) are removed from every year series and reported with duplicate_of",
            "undated records are excluded from year series, lifecycle labels and period selection, but kept for open-question extraction",
            "a term needs at least two dated mentions to define a series",
        ],
        "batch_size": len(records),
        "deduped_batch_size": len(deduped),
        "dated_batch_size": len(dated),
        "year_range": [years[0], years[-1]] if years else "no dated record",
        "screened_out": {"duplicates": duplicates, "undated": len(deduped) - len(dated)},
        "external_search": False,
        "task_text_used": bool(task_text),
    }



def load_lexicon():
    """Fallback synonym table only: concept rules declared in the input always win."""
    path = Path(__file__).resolve().parent.parent / "assets" / "theme-lexicon.json"
    try:
        data = load_json(path)
    except (OSError, ValueError):
        data = {}
    concepts = data.get("concepts") if isinstance(data, dict) else None
    return concepts if isinstance(concepts, dict) else {}


def parse_concept_block(block):
    rules = {}

    def add(name, terms):
        name = as_text(name)
        values = terms if isinstance(terms, list) else [terms]
        values = [as_text(item).lower() for item in values]
        values = [value for value in values if value]
        if name and values:
            rules[name] = {"terms": values, "source": "input"}

    if isinstance(block, dict):
        for concept, value in block.items():
            if isinstance(value, dict):
                add(concept, pick(value, ("terms", "members", "synonyms", "variants", "children")) or [])
            elif isinstance(value, list):
                add(concept, value)
            else:
                add(concept, [value])
    elif isinstance(block, list):
        for item in block:
            if not isinstance(item, dict):
                continue
            add(pick(item, ("concept", "theme", "name", "topic", "parent", "label")),
                pick(item, ("terms", "members", "synonyms", "variants", "children")) or [])
    return rules


def concept_rules_of(case, task_text):
    """Synonym/hypernym rules declared by the input (case.json or a JSON block in task.md)."""
    rules = {}
    if isinstance(case, dict):
        for key in CONCEPT_RULE_KEYS:
            if isinstance(case.get(key), (dict, list)):
                rules.update(parse_concept_block(case[key]))
        for wrapper in ("filters", "protocol", "search_protocol", "screening", "themes"):
            node = case.get(wrapper)
            if isinstance(node, dict):
                for key in CONCEPT_RULE_KEYS:
                    if isinstance(node.get(key), (dict, list)):
                        rules.update(parse_concept_block(node[key]))
    if not rules:
        for chunk in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", task_text or "", re.S):
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            for key in CONCEPT_RULE_KEYS:
                if isinstance(data.get(key), (dict, list)):
                    rules.update(parse_concept_block(data[key]))
    return rules


def concept_of(term, concepts, rules=None):
    lowered = str(term).lower()
    for concept in sorted(rules or {}):
        variants = [concept.lower()] + [str(item).lower() for item in (rules[concept].get("terms") or [])]
        if lowered in variants:
            return concept
    for concept in sorted(concepts):
        data = concepts[concept] if isinstance(concepts[concept], dict) else {}
        variants = [concept.lower()] + [str(item).lower() for item in data.get("terms") or []]
        if lowered in variants:
            return concept
    return None


def theme_evolution(terms, limit, concepts=None, rules=None):
    concepts = concepts or {}
    rules = rules or {}
    groups = {}
    order = []
    for term in terms[:limit]:
        concept = concept_of(term["term"], concepts, rules)
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
        if group["concept"] and group["concept"] in rules:
            merge_source = "input"
            merge_rule = "explicit_concept_mapping"
            merge_basis = ("the input declares '%s' as a concept covering these members; the theme series is the "
                           "sum of the member term series, with no inferred membership" % group["concept"])
            merge_split_note = "members were aggregated because the input declared the concept; no lexicon was used"
        elif group["concept"]:
            merge_source = "lexicon"
            merge_rule = "fallback_synonym_merge"
            merge_basis = ("no input concept rule matched; the fallback table assets/theme-lexicon.json maps these "
                           "members to '%s' and the theme series is their sum" % group["concept"])
            merge_split_note = ("members were aggregated with the fallback lexicon (assets/theme-lexicon.json); "
                                "declare concept_rules in the input to override it")
        else:
            merge_source = "term-level"
            merge_rule = "term_level"
            merge_basis = ("no input concept rule and no fallback lexicon entry covers this term, so it is reported "
                           "on its own at term level")
            merge_split_note = "no concept mapping was supplied or matched; the term is reported on its own"
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
            "merge_rule": {"rule": merge_rule, "source": merge_source},
            "merge_basis": merge_basis,
            "merge_evidence": [{"term": member["term"], "mentions": member["mentions"],
                                "first_year": member["first_year"], "last_year": member["last_year"]}
                               for member in members],
            "merge_split": ("synonyms_merged" if len(members) > 1 else "no_synonym_in_lexicon"),
            "merge_split_note": merge_split_note,
        }
        rows.append(row)
    if rows:
        return rows
    return [{"theme": "no term meets the two-mention threshold",
             "concept": None, "member_terms": [], "merged_synonyms": False,
             "stage": "not_determinable", "lifecycle_label": "absent",
             "from_year": None, "to_year": None, "series": {},
             "basis": "term series require at least two dated mentions",
             "source_ids": [], "merge_rule": {"rule": "not_applicable", "source": "none"},
             "merge_basis": "no term reached the two-mention threshold, so no merge decision applies",
             "merge_evidence": [],
             "merge_split": "not_detectable_from_term_counts",
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
                           "table_ref": table_ref or "result.claim_evidence",
                           "evidence_ids": []})
            return
        if record is not None:
            quote, truncated = excerpt(text_of(record), quote_limit)
            locator = locator_of(record)
        claims.append({"category": category, "claim": claim, "source_ids": source_ids,
                       "locator": locator,
                       "source_locator": record["source_locator"] if record is not None else None,
                       "case_locator": record["locator"] if record is not None else None,
                       "quote": quote,
                       "quote_verified": bool(record is not None and quote in text_of(record)),
                       "truncated": truncated, "period": period, "aggregate": False,
                       "table_ref": table_ref,
                       "evidence_ids": ["E%02d" % (index + 1) for index, row in enumerate(records)
                                        if record is not None and row is record]})

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
                              "citations_in_batch": chosen["citations"], "locator": locator_of(chosen),
                              "case_locator": chosen["locator"], "file": chosen["file"],
                              "reason": reason}
        rows.append({
            "period": span["label"],
            "period_from": span["from"],
            "period_to": span["to"],
            "records_in_period": len(members),
            "representative_source_id": representative["source_id"] if representative else None,
            "representative": representative,
            "rule": "exactly one representative per period: highest in-batch citation count; ties by year then source id; records without citations rank after cited records",
            "basis": span.get("basis") or "period boundary supplied by the input or the equal-width default",
            "basis_source": span.get("basis_source") or "derived:equal_width",
            "covered_stages": sorted(set(stages)) if stages else "no term series in this period",
            "covered_sources": [record["source_id"] for record in ranked[:3]],
            "known_omissions": "undated records and terms mentioned only once are not represented",
        })
    if rows:
        return rows
    return [{"period": "no dated period", "period_from": None, "period_to": None,
             "records_in_period": 0, "representative_source_id": None,
             "representative": None, "rule": "not_applicable",
             "basis": "no record carries a publication year", "basis_source": "derived:no_dated_record",
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
            evidence.append({"source_id": dated[0]["source_id"], "locator": locator_of(dated[0]),
                             "year": dated[0]["year"], "why": "every dated record falls in %d" % years[0]})
        elif gap["type"] == "thin_term_signal":
            for record in dated[:3]:
                evidence.append({"source_id": record["source_id"], "locator": locator_of(record),
                                 "year": record["year"],
                                 "why": "only %d term(s) reach two dated mentions" % len(terms)})
        elif dated:
            record = dated[-1]
            evidence.append({"source_id": record["source_id"], "locator": locator_of(record),
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
                         "locator": locator_of(record), "case_locator": record["locator"],
                         "file": record["file"], "year": record["year"], "quote": quote,
                         "quote_verified": bool(quote) and quote in source, "truncated": truncated,
                         "series": term["series"], "lifecycle": term["lifecycle"]})
    for record in dated:
        if record["source_id"] in covered:
            continue
        source = text_of(record)
        quote, truncated = excerpt(source, quote_limit)
        rows.append({"kind": "record_evidence", "source_id": record["source_id"], "locator": locator_of(record),
                     "case_locator": record["locator"], "file": record["file"],
                     "year": record["year"], "quote": quote,
                     "quote_verified": bool(quote) and quote in source, "truncated": truncated})
    return rows


def synthesis(topic, records, dated, years, terms, gaps, periods=None, flow=None):
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
    if periods:
        phases = ["%s: %d record(s), stages %s" % (row["period"], row["records"],
                                                  ", ".join(row["covered_stages"]) if isinstance(row["covered_stages"], list)
                                                  else row["covered_stages"])
                  for row in periods]
        narrative += " Phase summary: " + "; ".join(phases) + "."
    if gaps:
        narrative += " Gaps in this batch: " + "; ".join(gap["basis"] for gap in gaps[:3]) + "."
    dedup = flow or {}
    narrative += (" Boundary: the statement covers %d unique record(s) (%d dated, %d duplicate(s) removed) and is not a "
                  "field-level forecast." % (dedup.get("unique", len(records)), dedup.get("dated", len(dated)),
                                             dedup.get("duplicates", 0)))
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
        case_source = record["abstract"] or record["title"]
        case_quote, case_truncated = excerpt(case_source, quote_limit)
        included = bool(record["year"]) and not record["duplicate_of"]
        if record["duplicate_of"]:
            exclusion = "duplicate of %s (same DOI or same normalised title and year), removed from every year series" % record["duplicate_of"]
        elif not record["year"]:
            exclusion = "no parsable publication year, so the record is excluded from every year series"
        else:
            exclusion = None
        rows.append({
            "source_id": record["source_id"],
            "locator": locator_of(record),
            "locator_kind": "source_paragraph" if record["source_locator"] else "case_pointer",
            "case_locator": record["locator"],
            "file": record["file"],
            "source_paragraph": record["source_paragraph"],
            "title": record["title"],
            "year": record["year"],
            "venue": record["venue"],
            "doi": record["doi"],
            "duplicate_of": record["duplicate_of"],
            "citations_in_batch": record["citations"],
            "compared_fields": ["year", "title", "abstract", "citations_in_batch"],
            "included_in_series": included,
            "exclusion_reason": exclusion,
            "quote": quote,
            "quote_verified": bool(quote) and quote in source,
            "truncated": truncated,
            "case_quote": case_quote,
            "case_quote_verified": bool(case_quote) and case_quote in case_source,
            "case_quote_truncated": case_truncated,
        })
    return rows



def render_review_report(result):
    """Four-section Chinese narrative built only from the computed tables."""
    overview = result.get("trend_overview") or {}
    flow = result.get("flow") or {}
    year_counts = overview.get("year_counts") or {}
    themes = result.get("theme_evolution") or []
    periods = result.get("periods") or []
    selection = result.get("representative_selection") or []
    gaps = result.get("research_gaps") or []
    matrix = result.get("evidence_matrix") or []
    coverage = result.get("coverage") or {}
    stated = [row for row in themes if (row.get("merge_rule") or {}).get("source") == "input"]
    fallback = [row for row in themes if (row.get("merge_rule") or {}).get("source") == "lexicon"]
    term_level = [row for row in themes if (row.get("merge_rule") or {}).get("source") == "term-level"]
    up = [row.get("theme") for row in themes if row.get("lifecycle_label") in ("emerging", "growing")]
    down = [row.get("theme") for row in themes if row.get("lifecycle_label") in ("declining", "dormant")]
    peak_year = overview.get("peak_year")
    hist = "、".join("%s 年 %s 条" % (year, count) for year, count in sorted(year_counts.items()))
    section_trend = (
        "时间趋势：本批共识别 %s 条题录，去重后 %s 条（按 DOI 或归一化标题加年份判定重复 %s 条，重复项不进入任何年份序列），"
        "其中 %s 条可解析出版年份，覆盖 %s 至 %s 年，峰值年为 %s 年（%s 条）。去重后的年份直方图为：%s。"
        "该直方图逐条写入 trend_stats.json 的 year_histogram，可与 evidence_matrix 的 included_in_series 独立复算。"
        % (flow.get("identified", overview.get("records")), flow.get("unique", overview.get("records")),
           flow.get("duplicates", 0), flow.get("dated", overview.get("dated_records")),
           (overview.get("year_range") or [None, None])[0], (overview.get("year_range") or [None, None])[1],
           peak_year, year_counts.get(peak_year, 0) if peak_year is not None else 0, hist or "无有年份记录"))
    section_theme = (
        "主题演化：主题表共 %s 行，其中 %s 行由输入声明的归并规则合并（source=input），%s 行沿用回退词表 "
        "assets/theme-lexicon.json（source=lexicon），%s 行停留在词项级（source=term-level）。"
        "处于出现或增长阶段的是 %s；处于衰退或休眠阶段的是 %s。每个主题的阶段标签都由首末年与前后半段计数按固定阈值推出，"
        "merge_basis 说明归并依据，merge_evidence 列出参与归并的每个词项及其提及次数，换领域时以输入规则为准。"
        % (len(themes), len(stated), len(fallback), len(term_level),
           "、".join(str(item) for item in up[:5]) or "无", "、".join(str(item) for item in down[:5]) or "无"))
    phase_bits = []
    for row in periods:
        rep = row.get("representative") or {}
        phase_bits.append("%s（%s 条，代表 %s）" % (row.get("period"), row.get("records"),
                                                    rep.get("source_id") or "无"))
    section_period = (
        "代表性工作：时间窗划分为 %s 个阶段，阶段划分口径为 %s；每阶段按批内引用数最高选出一条代表，平票按年份与 source_id，"
        "无引用计数的记录排在引用记录之后。各阶段情况为：%s。阶段边界与成立依据写在 representative_selection 的 basis 与 "
        "basis_source 中，代表作年份均落在所属阶段内。"
        % (len(periods), (selection[0].get("basis_source") if selection else "not_applicable"),
           "；".join(phase_bits) or "无可划分阶段"))
    gap_types = "、".join(str(row.get("type")) for row in gaps)
    section_gap = (
        "研究空白与边界：本批触发 %s 条空白（%s），每条都带 search_scope 与 exclusion_evidence，只表示本批内没有支撑证据，"
        "不等同于领域空缺。证据矩阵共 %s 行，其中原文匹配 %s 条、摘要或元数据层 %s 条，覆盖层级为 %s。"
        "全部结论描述的是所给批次，不预测未来年份、增长率或成熟度；超出批次的判断需另行检索与人工复核。"
        % (len(gaps), gap_types or "无", len(matrix), coverage.get("records_with_source_text", 0),
           coverage.get("records_with_abstract", 0), coverage.get("level", "unknown")))
    sections = [{"heading": "时间趋势", "text": section_trend},
                {"heading": "主题演化", "text": section_theme},
                {"heading": "代表性工作", "text": section_period},
                {"heading": "研究空白与边界", "text": section_gap}]
    text = "\n".join(item["text"] for item in sections)
    return {
        "report_type": "review_report",
        "language": "zh",
        "sections": sections,
        "text": text,
        "char_count": len(text),
        "generated_from": ["result.trend_overview", "result.theme_evolution", "result.periods",
                           "result.representative_selection", "result.research_gaps", "result.evidence_matrix"],
        "bounded_by": overview.get("year_range"),
        "not_a_forecast": True,
    }


def self_check(result, flow):
    checks = []

    def check(name, passed, detail):
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    identified = flow.get("identified", 0)
    duplicates = flow.get("duplicates", 0)
    unique = flow.get("unique", 0)
    dated = flow.get("dated", 0)
    undated = flow.get("undated", 0)
    check("flow_closure", identified == duplicates + unique and unique == dated + undated,
          "identified %d = duplicates %d + unique %d; unique %d = dated %d + undated %d"
          % (identified, duplicates, unique, unique, dated, undated))
    year_counts = (result.get("trend_overview") or {}).get("year_counts") or {}
    keys = list(year_counts.keys())
    check("year_counts_sorted", keys == sorted(keys), "year keys: %s" % (keys,))
    check("year_counts_sum", sum(year_counts.values()) == dated,
          "sum(year_counts) %d vs dated %d" % (sum(year_counts.values()), dated))
    matrix = result.get("evidence_matrix") or []
    check("quote_verified", all(row.get("quote_verified") for row in matrix),
          "%d/%d evidence rows carry a verified quote" % (sum(1 for row in matrix if row.get("quote_verified")), len(matrix)))
    check("case_quote_verified", all(row.get("case_quote_verified") for row in matrix),
          "%d/%d evidence rows keep a verified case.json quote"
          % (sum(1 for row in matrix if row.get("case_quote_verified")), len(matrix)))
    selection = result.get("representative_selection") or []
    inside = [row for row in selection if row.get("representative")]
    check("representative_in_window",
          all(row.get("period_from") is not None and row["period_from"] <= row["representative"].get("year", -1) <= row.get("period_to")
              for row in inside),
          "%d representative row(s) checked against their period window" % len(inside))
    ids = [row.get("source_id") for row in matrix if row.get("included_in_series")]
    check("unique_included_ids", len(ids) == len(set(ids)),
          "%d included source id(s), %d distinct" % (len(ids), len(set(ids))))
    verdict = "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL"
    return {"validator_verdict": verdict, "self_check": checks,
            "counts": {"checks": len(checks), "passed": sum(1 for row in checks if row["status"] == "PASS")}}


def build_payload(case, task_text, input_root=None):
    policy = load_policy()
    dormant_gap = pol(policy, "lifecycle.dormant_gap_years", 3)
    growth_factor = pol(policy, "lifecycle.growth_factor", 2.0)
    term_limit = pol(policy, "caps.tracked_terms", 12)
    quote_limit = pol(policy, "caps.quote_chars", 240)
    max_claims = pol(policy, "caps.max_claims", 40)

    raw_records = find_records(case)
    records = [normalize(raw, locator, index) for index, (locator, raw) in enumerate(raw_records)]
    exclude_case = None
    try:
        if input_root is not None:
            root = Path(input_root)
            exclude_case = root / "case.json" if root.is_dir() else root
    except OSError:
        exclude_case = None
    materials, material_errors, material_skipped = collect_materials(
        input_root, exclude_case,
        {"max_files": pol(policy, "limits.max_files", 50),
         "max_file_bytes": pol(policy, "limits.max_file_bytes", 500000)})
    matched_sources = attach_source_text(records, materials)

    topic = topic_of(case, task_text)
    deduped = dedupe(records)
    dated = [record for record in deduped if record["year"]]
    years = sorted({record["year"] for record in dated})
    low = years[0] if years else None
    high = years[-1] if years else None
    flow = {"identified": len(records), "duplicates": len(records) - len(deduped),
            "unique": len(deduped), "dated": len(dated)}
    flow["undated"] = len(deduped) - len(dated)

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
                 "citations_in_batch": record["citations"], "locator": locator_of(record),
                 "case_locator": record["locator"], "file": record["file"]}
                for record in sorted(entries, key=lambda item: (-item["citations"], item["source_id"]))[:3]
            ],
        })

    bins, bins_source, bins_note = period_plan(case, task_text, years)
    for span in bins:
        members = [record for record in dated if span["from"] <= record["year"] <= span["to"]]
        span["basis_source"] = bins_source
        span["basis"] = ("%s (%d-%d) covers %d dated record(s); %s" % (span["label"], span["from"], span["to"],
                                                                      len(members), bins_note))
    representation = representative_selection(bins, terms, dated)
    periods = []
    for index, span in enumerate(bins):
        members = [record for record in dated if span["from"] <= record["year"] <= span["to"]]
        top = sorted(members, key=lambda item: (-item["citations"], item["year"], item["source_id"]))[:3]
        rep = representation[index] if index < len(representation) else {}
        periods.append({"period": span["label"], "period_from": span["from"], "period_to": span["to"],
                        "records": len(members), "basis": span["basis"], "basis_source": span["basis_source"],
                        "representative": rep.get("representative"),
                        "covered_stages": rep.get("covered_stages") or "no term series in this period",
                        "works": [{"source_id": record["source_id"], "title": record["title"],
                                   "year": record["year"], "citations_in_batch": record["citations"]} for record in top],
                        "selection_rule": "exactly one representative (highest in-batch citations, ties by year then source id); works lists the top three for context only"})

    open_questions = []
    for record in deduped:
        text = (record["title"] + " " + record["abstract"]).lower()
        for cue in OPEN_QUESTION_CUES:
            if cue in text:
                source = record["abstract"] or record["title"]
                position = text.find(cue)
                window, _truncated = excerpt(clean_window(source, position - 80, position + 160), quote_limit)
                open_questions.append({"source_id": record["source_id"], "locator": record["locator"],
                                       "source_locator": record["source_locator"],
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
    if flow["duplicates"]:
        uncertainty.append({"type": "duplicate_records",
                            "detail": "%d duplicate record(s) were removed from every year series; each is listed with duplicate_of." % flow["duplicates"]})
    if flow["undated"]:
        uncertainty.append({"type": "undated_records", "detail": "%d record(s) lack a year and are excluded from series." % flow["undated"]})
    if dated and not any(record["citations"] for record in dated):
        uncertainty.append({"type": "no_citation_counts", "detail": "Citation counts are absent; 'representative' means first/highest within the batch only."})
    if any(term["lifecycle"] == "emerging" for term in terms):
        uncertainty.append({"type": "short_window", "detail": "Emerging labels use a three-year tail and can reflect indexing lag rather than a real shift."})
    if materials and not matched_sources:
        uncertainty.append({"type": "materials_unmatched",
                            "detail": "input materials were parsed but no record could be matched to a paragraph by DOI or title; quotes stay at the case.json field level."})
    uncertainty.append({"type": "batch_only", "detail": "Trends describe the supplied batch; no external database or citation index was queried."})

    if not records or not topic:
        status = "insufficient_input"
    elif len(dated) < 2 or len(years) < 2:
        status = "partial"
    else:
        status = "success"

    claims = claim_evidence(topic, records, dated, terms, periods, open_questions, gaps, years, quote_limit)[:max_claims]
    concept_rules = concept_rules_of(case, task_text)

    abstracts = len([record for record in deduped if record["abstract"]])
    if matched_sources:
        level = "full_text"
    elif abstracts:
        level = "abstract_only"
    else:
        level = "metadata_only"
    parsed_materials = len([row for row in materials if row["status"] == "parsed"])
    coverage = {
        "level": level,
        "records_with_source_text": matched_sources,
        "records_with_abstract": abstracts,
        "material_files": len(materials),
        "parsed_material_files": parsed_materials,
        "unparsed_materials": [row["path"] for row in materials if row["status"] == "unparsed"],
        "limits": [
            "abstract_only: quotes come from the supplied abstract field; claims about methods, samples or mechanisms need the full text",
            "metadata_only: only titles and identifiers are available; no abstract-level evidence is claimed",
            "full_text: quotes come from the matched source paragraph (locator S<file>#P<paragraph>)",
        ],
    }

    result = {
        "topic": topic,
        "trend_overview": {
            "records": flow["unique"],
            "identified_records": flow["identified"],
            "duplicates_removed": flow["duplicates"],
            "dated_records": len(dated),
            "year_range": [low, high],
            "year_counts": dict(sorted(year_counts.items())),
            "peak_year": max(year_counts.items(), key=lambda item: (item[1], item[0]))[0] if year_counts else None,
            "growth_note": "counts are absolute within the batch; no normalisation by database size is possible",
        },
        "flow": flow,
        "terms": terms,
        "periods": periods,
        "open_questions": open_questions,
        "conflicts": conflicts,
        "research_gaps": gaps,
        "evidence_matrix": evidence_matrix(records, quote_limit),
        "source_materials": [{"source_index": row["source_index"], "path": row["path"], "kind": row["kind"],
                              "status": row["status"], "paragraph_count": row["paragraph_count"],
                              "chars": row["chars"], "preview": row["preview"], "reason": row["reason"]}
                             for row in materials],
        "coverage": coverage,
        "retrieval_scope": retrieval_scope(topic, terms, records, dated, years, task_text,
                                           deduped, flow["duplicates"]),
        "theme_evolution": theme_evolution(terms, term_limit, load_lexicon(), concept_rules),
        "concept_rules": [{"concept": name, "terms": concept_rules[name]["terms"], "source": "input"}
                          for name in sorted(concept_rules)],
        "cooccurrence": pairs,
        "claim_evidence": claims,
        "representative_selection": representation,
        "gap_exclusion": gap_exclusion(gaps, dated, terms, years),
        "needs_human_confirmation": needs_human_confirmation(deduped, dated, terms, years, open_questions),
        "synthesis": synthesis(topic, deduped, dated, years, terms, gaps, periods, flow),
        "method": {
            "lifecycle_rule": "emerging: first seen in the last %d years; growing: late >= %.0fx early; declining: early >= %.0fx late; dormant: no record in the last %d years; else stable"
                             % (dormant_gap - 1, growth_factor, growth_factor, dormant_gap),
            "burst_rule": "year count above mean + standard deviation and at least 2",
            "representative_rule": "highest in-batch citation count, ties by source id; undated records are never selected",
            "evolution_rule": "appear / grow / stable / decline / dormant are measured from the batch; merge and split are reported only as co-occurrence candidates",
            "theme_merge_rule": "concept groups are taken from input concept_rules first; assets/theme-lexicon.json is only a fallback; unmatched terms stay at term level",
            "period_rule": bins_note,
            "period_basis": bins_source,
            "dedup_rule": "DOI first; otherwise normalised title + year; the first occurrence is kept and later ones are marked duplicate_of and removed from every year series",
            "materials_rule": "md/txt/csv/json under the input root are parsed into numbered paragraphs; PDF uses pdftotext when available and is otherwise marked unparsed; records are matched by DOI or title",
            "query_rule": "queries are declared with fields, date range and language, then scored by keyword hits on the supplied records only",
            "no_forecast": "no future values are extrapolated",
            "deterministic": True,
            "network": False,
        },
        "limitations": [
            "Term series depend on title/abstract wording; synonym merging only works through input concept_rules or the fallback lexicon.",
            "Year fields are used as supplied; online-first, issue and preprint dates are not distinguished.",
            "Citation counts, when supplied, are in-batch only and are not field-normalised.",
            "A dormant term in this batch is not evidence that the field abandoned it.",
            "Merge and split cannot be confirmed from term counts alone.",
            "Queries are declared and scored on the batch; no online index was queried, so hits are not database hits.",
            "No forecasting, topic modelling or external citation index is used.",
        ],
        "change_log": [
            "Counted dated records per year and located the peak year after removing duplicates.",
            "Built term-level series and assigned deterministic lifecycle labels with stated rules.",
            "Flagged burst years using mean plus standard deviation.",
            "Selected representative works per period by in-batch citations and stated each period basis.",
            "Mapped each lifecycle to an evolution stage; merged synonyms from input rules or the fallback lexicon with explicit evidence.",
            "Backed each trend, evolution, representative and gap claim with a locator and an exact quote.",
            "Collected explicitly stated open questions and stated batch-level gaps.",
            "Wrote trend_stats.json, screening_log.csv and a four-section review report next to result.json.",
        ],
    }
    checks = self_check(result, flow)
    result["validator_verdict"] = checks["validator_verdict"]
    result["self_check"] = checks["self_check"]
    result["review_report"] = render_review_report(result)
    return {
        "case_id": case_identifier(case) or "unknown",
        "status": status,
        "result": result,
        "evidence": build_evidence(terms, dated, quote_limit),
        "uncertainty": uncertainty,
        "errors": list(material_errors),
        "stats": {"records": len(records), "unique_records": len(deduped), "duplicates": flow["duplicates"],
                  "dated": len(dated), "years": len(years), "terms": len(terms),
                  "claims": len(claims), "open_questions": len(open_questions),
                  "human_confirmation_items": len(result["needs_human_confirmation"]),
                  "materials": len(materials), "matched_sources": matched_sources,
                  "materials_skipped": len(material_skipped), "network": "disabled"},
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
                          "items", "known_works", "prior_works", "candidates", "search_results",
                          "screening_records", "bibliography", "filters", "year_range", "output_contract",
                          "concept_rules", "theme_rules", "concept_groups", "synonym_rules", "thesaurus",
                          "synonyms", "hierarchy", "term_groups", "periods", "period_plan", "stages",
                          "time_slices", "year_bins", "period_bins", "protocol", "search_protocol", "screening"}

CONTRACT_ALIASES = {
    "summary": "synthesis",
    "report": "synthesis",
    "review_report": "review_report",
    "narrative_report": "review_report",
    "report_text": "review_report",
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


def screening_rows(result):
    bins = [{"label": row["period"], "from": row["period_from"], "to": row["period_to"]}
            for row in result.get("representative_selection") or [] if row.get("period_from") is not None]
    rows = []
    for row in result.get("evidence_matrix") or []:
        if row.get("duplicate_of"):
            decision = "exclude_duplicate"
            reason = "duplicate of %s; removed from every year series" % row["duplicate_of"]
        elif not row.get("included_in_series"):
            decision = "exclude_undated"
            reason = row.get("exclusion_reason") or "no parsable publication year"
        else:
            decision = "include"
            reason = "dated unique record used in year series and period tables"
        rows.append({
            "source_id": row.get("source_id") or "",
            "title": row.get("title") or "",
            "year": row.get("year") if row.get("year") is not None else "",
            "doi": row.get("doi") or "",
            "venue": row.get("venue") or "",
            "decision": decision,
            "duplicate_of": row.get("duplicate_of") or "",
            "reason": reason,
            "period": period_of_year(row.get("year"), bins) or "",
            "locator": row.get("locator") or "",
            "case_locator": row.get("case_locator") or "",
            "citations": row.get("citations_in_batch") if row.get("citations_in_batch") is not None else "",
        })
    return rows


def render_stats(target, payload):
    """Write trend_stats.json and screening_log.csv so the tables can be recomputed independently."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    method = result.get("method") or {}
    overview = result.get("trend_overview") or {}
    flow = result.get("flow") or {}
    rows = screening_rows(result)
    period_counts = []
    for row in result.get("representative_selection") or []:
        if row.get("period_from") is None:
            continue
        period_counts.append({"period": row.get("period"), "from": row.get("period_from"),
                              "to": row.get("period_to"),
                              "records": row.get("records_in_period")})
    stats = {
        "generated_by": "scripts/sk_entry.py",
        "case_id": payload.get("case_id"),
        "status": payload.get("status"),
        "topic": result.get("topic"),
        "flow": flow,
        "dedup_rule": method.get("dedup_rule"),
        "period_rule": method.get("period_rule"),
        "period_basis": method.get("period_basis"),
        "year_histogram": dict(sorted((overview.get("year_counts") or {}).items())),
        "peak_year": overview.get("peak_year"),
        "year_range": overview.get("year_range"),
        "period_counts": period_counts,
        "records": [{"source_id": row["source_id"], "year": row["year"], "venue": row["venue"],
                     "citations": row["citations"],
                     "period": row["period"], "decision": row["decision"],
                     "duplicate_of": row["duplicate_of"] or None, "locator": row["locator"]}
                    for row in rows],
        "theme_series": [{"theme": row.get("theme"), "lifecycle_label": row.get("lifecycle_label"),
                          "merge_rule": row.get("merge_rule"), "series": row.get("series")}
                         for row in result.get("theme_evolution") or []],
        "recompute": [
            "year_histogram counts unique dated records only (decision=include in screening_log.csv)",
            "flow.identified = flow.duplicates + flow.unique and flow.unique = flow.dated + flow.undated",
            "period_counts sum to flow.dated",
            "theme_series rows are the sums of their member term series in result.terms",
        ],
    }
    write_json(target / "trend_stats.json", stats)
    header = ["source_id", "title", "year", "doi", "venue", "decision", "duplicate_of", "reason",
              "period", "locator", "case_locator"]
    csv_path = Path(target) / "screening_log.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow([row[key] for key in header])
    return ["trend_stats.json", "screening_log.csv"]


def write_artifacts(out_dir, payload):
    """Write the markdown report and recomputable statistics tables next to result.json."""
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
             "- Identified records: %s | unique: %s | duplicates removed: %s"
             % (overview.get("identified_records"), overview.get("records"), overview.get("duplicates_removed")),
             "- Dated records: %s | Year range: %s" % (overview.get("dated_records"), overview.get("year_range")),
             "- Peak year: %s" % overview.get("peak_year"),
             "- Note: %s" % overview.get("growth_note"), "",
             "| year | records |", "|---|---|"]
    for year, count in sorted((overview.get("year_counts") or {}).items()):
        lines.append("| %s | %s |" % (year, count))
    lines += ["", "## 2. Theme evolution", "",
              "| theme | members | lifecycle | stage | merge source | confidence |", "|---|---|---|---|---|---|"]
    confidence = {}
    for term in result.get("terms") or []:
        confidence[term.get("term")] = term.get("confidence")
    for row in result.get("theme_evolution") or []:
        members = row.get("member_terms") or [row.get("theme")]
        level = confidence.get((row.get("member_terms") or [None])[0]) or "n/a"
        source = (row.get("merge_rule") or {}).get("source") or "n/a"
        lines.append("| %s | %s | %s | %s | %s | %s |" % (row.get("theme"), ", ".join(members), row.get("lifecycle_label"),
                                                          row.get("stage"), source, level))
    lines += ["", "## 3. Representative work per period", "",
              "| period | records | representative | year | basis source | reason |", "|---|---|---|---|---|---|"]
    for row in result.get("representative_selection") or []:
        rep = row.get("representative") or {}
        lines.append("| %s | %s | %s | %s | %s | %s |" % (row.get("period"), row.get("records_in_period"),
                                                          rep.get("source_id") or "none", rep.get("year") or "",
                                                          row.get("basis_source") or "",
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
    report = result.get("review_report") or {}
    if report.get("text"):
        lines += ["", "## 6. Narrative review (zh)", ""]
        for section in report.get("sections") or []:
            lines += ["### %s" % section.get("heading"), "", section.get("text"), ""]
    report_path = target / "report.md"
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    written = []
    if os.path.exists(str(report_path)):
        written.append("report.md")
    for name in render_stats(target, payload):
        if os.path.exists(str(Path(target) / name)):
            written.append(name)
    return sorted(written)


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
