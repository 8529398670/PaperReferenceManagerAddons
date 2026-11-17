"""Screen one paper and pull its details out of its text: the old
src/review/classify.py, extract.py and datasets.py, reading every word list
and number from the rules (app/review/rules.py) instead of constants.

Inclusion needs all three:
  1. fMRI/BOLD is the dominant modality (not merely mentioned),
  2. the paper decodes (fMRI in, stimulus / content / label out),
  3. transformer / attention machinery sits in the model the authors built.

Each verdict carries its "why": every test, the counts it saw, and the bar it
had to clear, so the page can say exactly what decided it. Each extracted value
carries the sentence it came from. A blank means the paper does not say.
"""
from __future__ import annotations

import bisect
import re
from typing import Any

from app.review.rules import Rules

WS = re.compile(r"\s+")


def clean(s: Any) -> str:
    return WS.sub(" ", str(s or "")).strip()


def count(text: str, alt: re.Pattern[str] | None) -> int:
    if alt is None or not text:
        return 0
    return sum(1 for _ in alt.finditer(text))


def first_hits(text: str, patterns: tuple[re.Pattern[str], ...], limit: int = 3, width: int = 240) -> list[str]:
    out: list[str] = []
    for rx in patterns:
        m = rx.search(text)
        if m:
            a, b = max(0, m.start() - width // 2), min(len(text), m.end() + width // 2)
            out.append(clean(text[a:b]))
        if len(out) >= limit:
            break
    return out


def matched_terms(text: str, alt: re.Pattern[str] | None, limit: int = 8) -> list[str]:
    """The distinct words that matched, most frequent first: what the page
    shows beside a count."""
    if alt is None or not text:
        return []
    seen: dict[str, int] = {}
    for m in alt.finditer(text):
        word = clean(m.group(0))[:60]
        key = word.lower()
        seen[key] = seen.get(key, 0) + 1
    return [w for w, _ in sorted(seen.items(), key=lambda kv: -kv[1])[:limit]]


def near(text: str, a: re.Pattern[str] | None, b: re.Pattern[str] | None, window: float) -> bool:
    """Whether any a match sits within window characters of a b match."""
    if a is None or b is None:
        return False
    bs = sorted(m.start() for m in b.finditer(text))
    if not bs:
        return False
    for m in a.finditer(text):
        i = bisect.bisect_left(bs, m.start())
        for j in (i - 1, i):
            if 0 <= j < len(bs) and abs(m.start() - bs[j]) <= window:
                return True
    return False


def _join(*alts: re.Pattern[str] | None) -> re.Pattern[str] | None:
    parts = [a.pattern for a in alts if a is not None]
    return re.compile("|".join(f"(?:{p})" for p in parts), re.I) if parts else None


def _test(name: str, passed: bool, detail: str, terms: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"test": name, "pass": bool(passed), "detail": detail}
    if terms:
        out["terms"] = terms
    return out


def _n(v: float) -> str:
    return f"{v:g}"


# -- the full-text screen ---------------------------------------------------------------

def classify(rules: Rules, title: str, abstract: str, methods: str, body: str) -> dict[str, Any]:
    """Screen a paper whose text we hold. body is the paper up to its
    bibliography; methods its methods sections."""
    T = rules.full
    V = rules.vocab
    core = methods if len(methods) > T("methods_min_chars") else body
    full = body + "\n" + methods
    fmri_alt, other_alt = V["fmri_evidence"][1], V["other_modality"][1]
    built_alt, pre_alt, ours_alt = V["attn_built"][1], V["attn_pretrained"][1], V["ours"][1]

    # 1. fMRI, by dominance rather than mention.
    fmri_full, fmri_core = count(full, fmri_alt), count(core, fmri_alt)
    other_full, other_core = count(full, other_alt), count(core, other_alt)
    dom_core = fmri_core >= max(T("dom_core_min"), other_core * T("dom_core_ratio"))
    dom_full = fmri_full >= max(T("dom_full_min"), other_full * T("dom_full_ratio"))
    is_fmri = fmri_full >= T("fmri_full_min") and fmri_core >= T("fmri_core_min") and (dom_core or dom_full)
    multimodal = other_core >= T("multimodal_min") and fmri_core >= T("multimodal_min")

    # 2. attention in their own model.
    attn_methods = count(core, built_alt)
    attn_pre = count(core, pre_alt)
    attn_total = attn_methods + attn_pre
    ours = near(core, _join(built_alt, pre_alt), ours_alt, T("attn_near_window"))
    attn_built = (
        attn_methods >= T("attn_methods_min") or attn_total >= T("attn_total_min")
        or (attn_total >= T("attn_total_with_ours_min") and ours)
        or (attn_methods >= T("attn_methods_with_ours_min") and ours)
    )
    roles = [label for label, alt in rules.roles if count(core, alt)]

    # 3. decoding.
    scores = {
        name: T("task_weight_title") * count(title, alt) + T("task_weight_abstract") * count(abstract, alt) + T("task_weight_full") * count(full, alt)
        for name, _prio, _pats, alt in rules.tasks
    }
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    task = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    top = ranked[0][1] if ranked else 0
    is_decoding = top >= T("decoding_min")
    task_patterns = next((pats for name, _p, pats, _a in rules.tasks if name == task), ())

    # Exclusions, in order.
    survey_alt = rules.exclusions["survey"][1]
    survey_score = (T("survey_weight_title") * count(title, survey_alt) + T("survey_weight_abstract") * count(abstract, survey_alt)
                    + T("survey_weight_body") * count(body[: int(T("survey_body_chars"))], survey_alt))
    survey_title = bool(rules.survey_title.search(title or ""))
    survey = survey_title or survey_score >= T("survey_min")
    enc = count(full, rules.exclusions["encoding"][1])
    rec = count(full, rules.exclusions["reconstruction"][1])
    code = ""
    if survey:
        code = "survey"
    elif not is_fmri:
        code = "not_fmri"
    elif not attn_built:
        code = "no_attention"
    elif not is_decoding:
        code = "encoding" if enc >= T("encoding_min") else "reconstruction" if rec >= T("reconstruction_min") else "no_decoding"
    borderline = code == "no_attention" and T("borderline_attn_min") <= attn_total <= T("borderline_attn_max")

    why = [
        _test("primary paper", not survey,
              ("title reads as a review / survey" if survey_title else f"survey score {_n(survey_score)}")
              + f" (excluded at {_n(T('survey_min'))})", matched_terms(title + "\n" + abstract, survey_alt)),
        _test("fMRI dominant", is_fmri,
              f"fMRI evidence {fmri_full} overall (needs {_n(T('fmri_full_min'))}), {fmri_core} in methods (needs {_n(T('fmri_core_min'))}); "
              f"rival modalities {other_full} overall, {other_core} in methods; dominant in methods: {'yes' if dom_core else 'no'}, "
              f"overall: {'yes' if dom_full else 'no'}", matched_terms(core, fmri_alt)),
        _test("attention in their model", attn_built,
              f"{attn_methods} attention mentions and {attn_pre} pretrained-transformer mentions in methods; "
              f"attributed to the authors: {'yes' if ours else 'no'} (passes at {_n(T('attn_methods_min'))} attention, "
              f"{_n(T('attn_total_min'))} total, or {_n(T('attn_total_with_ours_min'))} total / {_n(T('attn_methods_with_ours_min'))} attention "
              f"when attributed)", matched_terms(core, _join(built_alt, pre_alt))),
        _test("decodes", is_decoding,
              f"best task {task or 'none'} scored {_n(top)} (needs {_n(T('decoding_min'))}); encoding phrases {enc}, reconstruction phrases {rec}",
              matched_terms(title + "\n" + abstract + "\n" + full, next((a for n, _p, _x, a in rules.tasks if n == task), None))),
    ]
    return {
        "include": not code,
        "reason_code": code,
        "reason": getattr(rules.doc.reasons, code) if code else "",
        "borderline": borderline,
        "criteria": {"fmri": bool(is_fmri), "attention": bool(attn_built), "decoding": bool(is_decoding), "primary": not survey},
        "task_category": task or "unclassified",
        "priority": rules.priority.get(task or "", rules.doc.unclassified_priority),
        "task_scores": scores,
        "attention_role": "; ".join(dict.fromkeys(roles)) or "unspecified",
        "screening": {
            "fmri_evidence_total": fmri_full, "fmri_evidence_methods": fmri_core, "fmri_strong": count(full, V["fmri_strong"][1]),
            "rival_modality_total": other_full, "rival_modality_methods": other_core, "multimodal": bool(multimodal),
            "attention_hits_methods": attn_methods, "pretrained_transformer_hits": attn_pre, "attention_total_methods": attn_total,
            "attention_body": count(body, built_alt), "attention_attributed_to_authors": bool(ours),
            "decoding_score": top, "survey_score": survey_score, "encoding_hits": enc, "reconstruction_hits": rec,
            "methods_chars": len(methods), "body_chars": len(body),
        },
        "task_evidence": first_hits(abstract + "\n" + full, task_patterns, limit=2) if task else [],
        "attention_evidence": first_hits(core, V["attn_built"][0], limit=2),
        "why": why,
    }


# -- the abstract-only screen -------------------------------------------------------------

def classify_abstract(rules: Rules, title: str, abstract: str) -> dict[str, Any]:
    """The same three criteria on a title and abstract alone, with thresholds
    sized for an abstract: fMRI is harder to establish (named once, if at
    all), attention easier to trust (no related-work section)."""
    T = rules.abstract
    V = rules.vocab
    title, abstract = title or "", abstract or ""
    text = title + "\n" + abstract
    fmri_alt, other_alt = V["fmri_evidence"][1], V["other_modality"][1]
    built_alt, pre_alt = V["attn_built"][1], V["attn_pretrained"][1]
    fmri, other = count(text, fmri_alt), count(text, other_alt)
    is_fmri = fmri >= T("fmri_min") and fmri >= other
    multimodal = fmri >= T("multimodal_min") and other >= T("multimodal_min")
    attn_b, attn_p = count(text, built_alt), count(text, pre_alt)
    attn_total = attn_b + attn_p
    ours = near(text, _join(built_alt, pre_alt), V["ours"][1], T("attn_near_window"))
    attn_built = attn_total >= T("attn_total_min")
    roles = [label for label, alt in rules.roles if count(text, alt)]
    scores = {
        name: T("task_weight_title") * count(title, alt) + T("task_weight_abstract") * count(abstract, alt)
        for name, _prio, _pats, alt in rules.tasks
    }
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    task = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    generic = count(text, V["decode_generic"][1])
    decode_score = (ranked[0][1] if ranked else 0) + generic
    is_decoding = decode_score >= T("decoding_min")
    survey_alt = rules.exclusions["survey"][1]
    survey_title = bool(rules.survey_title.search(title))
    survey_score = T("survey_weight_title") * count(title, survey_alt) + T("survey_weight_abstract") * count(abstract, survey_alt)
    survey = survey_title or survey_score >= T("survey_min")
    enc = count(text, rules.exclusions["encoding"][1])
    rec = count(text, rules.exclusions["reconstruction"][1])
    code = ""
    if survey:
        code = "survey"
    elif not is_fmri:
        code = "no_fmri_named" if fmri == 0 else "not_fmri"
    elif not attn_built:
        code = "no_attention_abstract"
    elif not is_decoding:
        code = "encoding" if enc >= T("encoding_min") else "reconstruction" if rec >= T("reconstruction_min") else "no_decoding"
    task_ev: list[str] = []
    attn_ev: list[str] = []
    if not code:
        task_patterns = next((pats for name, _p, pats, _a in rules.tasks if name == task), ())
        task_ev = first_hits(text, task_patterns, limit=2) if task else []
        if not task_ev and generic:
            task_ev = first_hits(text, V["decode_generic"][0], limit=2)
        attn_ev = first_hits(text, V["attn_built"][0] + V["attn_pretrained"][0], limit=2)
    why = [
        _test("primary paper", not survey,
              ("title reads as a review / survey" if survey_title else f"survey score {_n(survey_score)}") + f" (excluded at {_n(T('survey_min'))})"),
        _test("fMRI named", is_fmri, f"fMRI named {fmri} times (needs {_n(T('fmri_min'))}), rival modalities {other}", matched_terms(text, fmri_alt)),
        _test("attention named", attn_built,
              f"{attn_b} attention and {attn_p} pretrained-transformer mentions (needs {_n(T('attn_total_min'))} together)",
              matched_terms(text, _join(built_alt, pre_alt))),
        _test("decodes", is_decoding,
              f"best task {task or 'none'} {_n(decode_score - generic)} + generic decoding phrases {generic} = {_n(decode_score)} "
              f"(needs {_n(T('decoding_min'))})", matched_terms(text, V["decode_generic"][1])),
    ]
    return {
        "include": not code,
        "reason_code": code,
        "reason": getattr(rules.doc.reasons, code) if code else "",
        "borderline": False,
        "criteria": {"fmri": bool(is_fmri), "attention": bool(attn_built), "decoding": bool(is_decoding), "primary": not survey},
        "task_category": task or "unclassified",
        "priority": rules.priority.get(task or "", rules.doc.unclassified_priority),
        "task_scores": scores,
        "attention_role": "; ".join(dict.fromkeys(roles)) or "unspecified",
        "screening": {
            "fmri_evidence_total": fmri, "rival_modality_total": other, "multimodal": bool(multimodal),
            "attention_hits": attn_b, "pretrained_transformer_hits": attn_p, "attention_total": attn_total,
            "attention_attributed_to_authors": bool(ours), "decoding_score": decode_score, "decode_generic": generic,
            "survey_score": survey_score, "encoding_hits": enc, "reconstruction_hits": rec, "abstract_chars": len(abstract),
        },
        "task_evidence": task_ev,
        "attention_evidence": attn_ev,
        "why": why,
    }


def near_miss(result: dict[str, Any]) -> str:
    """The one criterion an excluded abstract failed when the other two held
    (and it is no survey), or ""."""
    crit = result.get("criteria") or {}
    if result.get("include") or not crit.get("primary", True):
        return ""
    failed = [k for k in ("fmri", "attention", "decoding") if not crit.get(k)]
    return failed[0] if len(failed) == 1 else ""


# -- extraction ---------------------------------------------------------------------------

def _as_int(rules: Rules, tok: str | None) -> int | None:
    if tok is None:
        return None
    t = tok.strip().lower()
    if t.isdigit():
        return int(t)
    return rules.word_numbers.get(t)


def _group(m: re.Match[str], name: str) -> str | None:
    try:
        if name.isdigit():
            return m.group(int(name))
        return m.group(name)
    except (IndexError, re.error):
        return None


def _fill(template: str, m: re.Match[str], extra: dict[str, str]) -> str | None:
    missing = False

    def one(found: re.Match[str]) -> str:
        nonlocal missing
        name = found.group(1)
        if name in extra:
            return extra[name]
        value = _group(m, name)
        if value is None:
            missing = True
            return ""
        return value

    out = re.sub(r"\$\{(\w+)\}", one, template)
    return None if missing else out


def post_value(rules: Rules, spec: Any, m: re.Match[str]) -> str | None:
    """A match -> the value shown, by the field's post rule; None drops it."""
    post = spec.post
    if post.kind == "seconds_or_ms":
        raw, unit = _group(m, "v"), (_group(m, "u") or "").lower()
        try:
            v = float(raw or "")
        except ValueError:
            return None
        value = f"{v:g} ms" if unit.startswith("ms") or (not unit and v > post.ms_above) else f"{v:g} s"
    elif post.kind == "count":
        n = _as_int(rules, _group(m, "v"))
        if not n:
            return None
        value = _fill(post.template, m, {"n": str(n)})
    elif post.kind == "negation" and spec.when is not None and spec.when.search(m.group(0)):
        value = post.value
    else:
        value = _fill(post.template, m, {})
    if value is None:
        return None
    value = clean(value)
    for old, new in post.replace.items():
        value = value.replace(old, new)
    if post.strip:
        value = value.rstrip(post.strip)
    if post.lower:
        value = value.lower()
    return value or None


def plausible(spec: Any, value: str) -> bool:
    gate = spec.plausible
    if gate is None:
        return True
    nums = re.findall(r"\d+(?:\.\d+)?", value)
    if not nums:
        return True
    unit = "ms" if "ms" in value else ("s" if re.search(r"\bs\b", value) else "")
    span = gate.range_seconds if unit == "s" and gate.range_seconds else gate.range
    if not span:
        return True
    return all(span[0] <= float(n) <= span[1] for n in nums)


def extract(rules: Rules, text: str) -> dict[str, dict[str, Any]]:
    """Every field: {values (most stated first), counts, evidence (quotes),
    dropped (implausible values)}. A field the paper never states is left
    out."""
    window = int(rules.ext("context_window"))
    quotes = int(rules.ext("evidence_quotes"))
    chars = int(rules.ext("evidence_chars"))
    out: dict[str, dict[str, Any]] = {}
    for spec in rules.fields:
        counts: dict[str, int] = {}
        spans: dict[str, str] = {}
        for rx in spec.patterns:
            for m in rx.finditer(text):
                value = post_value(rules, spec, m)
                if not value:
                    continue
                key = next((k for k in counts if k.lower() == value.lower()), value)
                counts[key] = counts.get(key, 0) + 1
                if key not in spans:
                    a, b = max(0, m.start() - window // 2), min(len(text), m.end() + window // 2)
                    spans[key] = clean(text[a:b])
        dropped = [v for v in counts if not plausible(spec, v)]
        for v in dropped:
            counts.pop(v)
            spans.pop(v, None)
        if not counts:
            if dropped:
                out[spec.name] = {"group": spec.group, "values": [], "counts": {}, "evidence": {}, "dropped": dropped}
            continue
        ranked = [v for v, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
        entry: dict[str, Any] = {
            "group": spec.group, "values": ranked, "counts": counts,
            "evidence": {v: spans[v][:chars] for v in ranked[:quotes] if v in spans},
        }
        if dropped:
            entry["dropped"] = dropped
        out[spec.name] = entry
    return out


# -- datasets -------------------------------------------------------------------------------

def detect_datasets(rules: Rules, text: str, min_hits: float) -> list[str]:
    out = []
    for name, pats in rules.datasets:
        if sum(len(rx.findall(text)) for rx in pats) >= min_hits:
            out.append(name)
    return out


def _norm_param(name: str, m: re.Match[str]) -> str | None:
    g = m.group(1)
    if g is None:
        return None
    if name in ("TR", "TE"):
        try:
            v = float(g)
        except ValueError:
            return None
        unit = ((m.group(2) if m.re.groups >= 2 else None) or "").lower()
        if unit.startswith("m") or (not unit and v > 50):
            return f"{v:g} ms"
        return f"{v:g} s" if v < 50 else None
    if name == "Flip_Angle":
        return f"{g}°"
    if name == "Field_Strength":
        return f"{g}T"
    if name == "Multiband":
        return f"MB {g}"
    if name == "N_Slices":
        return f"{g} slices"
    if name == "Voxel_Size":
        v = re.sub(r"\s+", "", g)
        return v if re.match(r"^\d", v) else None
    return clean(g)


def mine(rules: Rules, text: str) -> dict[str, dict[str, list[str]]]:
    """This paper's contribution to the dataset consensus: for each dataset it
    mentions, the acquisition values found near the mention.
    {dataset: {param: [values]}}"""
    window = int(rules.cons("window"))
    spots_max = int(rules.cons("max_spots"))
    voxel_max = rules.cons("voxel_max_mm")
    out: dict[str, dict[str, set[str]]] = {}
    for name, pats in rules.datasets:
        spots = [m.start() for rx in pats for m in rx.finditer(text)]
        for s in spots[:spots_max]:
            chunk = text[max(0, s - window): s + window]
            for pname, rx in rules.params:
                for m in rx.finditer(chunk):
                    if pname == "Voxel_Size":
                        left = chunk[max(0, m.start() - 40): m.start()]
                        if rules.voxel_noise_left.search(left):
                            continue
                        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(1) or "")]
                        if not nums or max(nums) > voxel_max:
                            continue
                    value = _norm_param(pname, m)
                    if value:
                        out.setdefault(name, {}).setdefault(pname, set()).add(value)
    return {ds: {p: sorted(v) for p, v in params.items()} for ds, params in out.items()}


# -- model name --------------------------------------------------------------------------------

def model_name(title: str, abstract: str) -> str:
    """What the authors call their model: the title's "Name: ..." first, then
    "we propose X" in the abstract."""
    t = title or ""
    m = re.match(r"^([A-Z][A-Za-z0-9+\-]{1,24}(?:\s?[A-Z][A-Za-z0-9]*)?)\s*[:—-]\s", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(?:we (?:propose|present|introduce)|call(?:ed)? it|named?)\s+([A-Z][A-Za-z0-9+\-]{2,24})\b", t)
    if m:
        return m.group(1)
    m = re.search(
        r"\b[Ww]e (?:propose|present|introduce|develop|design|build)\s+"
        r"(?:a\s+(?:novel\s+)?(?:model|framework|method)\s+(?:called|named|termed)\s+)?"
        r"([A-Z][A-Za-z0-9]*(?:[A-Z0-9][A-Za-z0-9+\-]*)+)\b", abstract or "")
    return m.group(1) if m else ""


# -- one paper ------------------------------------------------------------------------------------

def screen_paper(rules: Rules, title: str, abstract: str, methods: str, body: str) -> dict[str, Any]:
    """Everything the review stage stores for one paper."""
    if not (body.strip() or methods.strip()):
        verdict = {
            "include": False, "reason_code": "no_text", "reason": rules.doc.reasons.no_text, "borderline": False,
            "criteria": {}, "task_category": "unclassified", "priority": rules.doc.unclassified_priority,
            "why": [_test("text", False, "no text: Zotero has none for this paper and OCR has not run")],
        }
        return {"rules": rules.signature, "mode": "full", "verdict": verdict, "fields": {}, "datasets": [], "mined": {},
                "model_name": model_name(title, abstract)}
    verdict = classify(rules, title, abstract, methods, body)
    scan = (methods + "\n" + body)[: int(rules.ext("text_cap"))]
    return {
        "rules": rules.signature,
        "mode": "full",
        "verdict": verdict,
        "fields": extract(rules, scan),
        "datasets": detect_datasets(rules, body, rules.cons("min_hits_full")),
        "mined": mine(rules, body),
        "model_name": model_name(title, abstract),
    }


def screen_abstract(rules: Rules, title: str, abstract: str) -> dict[str, Any]:
    verdict = classify_abstract(rules, title, abstract)
    verdict["near_miss"] = near_miss(verdict)
    text = (title or "") + "\n" + (abstract or "")
    return {
        "rules": rules.signature,
        "mode": "abstract",
        "verdict": verdict,
        "fields": extract(rules, text),
        "datasets": detect_datasets(rules, text, rules.cons("min_hits_abstract")),
        "mined": {},
        "model_name": model_name(title, abstract),
    }


def summary(result: dict[str, Any]) -> dict[str, Any]:
    """The small part kept on the task row: badges and filters."""
    v = result.get("verdict") or {}
    return {
        "include": bool(v.get("include")), "borderline": bool(v.get("borderline")), "reason": v.get("reason_code", ""),
        "task": v.get("task_category", ""), "priority": v.get("priority"), "fields": len(result.get("fields") or {}),
        "datasets": list(result.get("datasets") or []),
    }
