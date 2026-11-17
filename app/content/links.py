"""Code links, data links and named public datasets, from a paper's text.

Three kinds of evidence, because papers give it in different ways:

  CODE    a URL (or a bare host/path) pointing at a code host -- GitHub,
          GitLab, Bitbucket, OSF, Zenodo, Code Ocean, Hugging Face, ...
  DATA    the same scan against a table of DATA archives -- OpenNeuro,
          NeuroVault, DANDI, PhysioNet, ConnectomeDB, ... -- plus bare
          OpenNeuro accessions (`ds000105`), minted into the record's URL.
          The generalists (Zenodo, OSF, Dryad, Figshare, Hugging Face) are in
          both tables on purpose: they host both, and that is the honest
          answer about what they are.
  NAMES   the dataset a paper NAMES but never links -- "we use HCP",
          "trained on NSD" -- matched against a fixed vocabulary.

Both link scans share ONE implementation of the hard part: the line-break
repair (a long URL split across two lines), the trailing-punctuation trim,
the "is this a real record" test and the de-dup. Only the host table differs.

Everything here is a pure function over strings. scan_paper() is the one call
per paper and decides which text each scan reads.
"""
from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

from app.content import sections

# ---------------------------------------------------------------------------
# Known code hosts -> label
# ---------------------------------------------------------------------------
# Order matters: more-specific subdomains (gist., raw.) come before the bare
# host so they win the first match in the classifier.
HOST_LABELS: tuple[tuple[str, str], ...] = (
    ("gist.github.com", "GitHub Gist"),
    ("raw.githubusercontent.com", "GitHub"),
    ("github.com", "GitHub"),
    ("github.io", "GitHub"),
    ("gitlab.com", "GitLab"),
    ("bitbucket.org", "Bitbucket"),
    ("osf.io", "OSF"),
    ("datadryad.org", "Dryad"),
    ("dryad.org", "Dryad"),
    ("zenodo.org", "Zenodo"),
    ("figshare.com", "Figshare"),
    ("codeocean.com", "Code Ocean"),
    ("sourceforge.net", "SourceForge"),
    ("huggingface.co", "Hugging Face"),
    ("gitee.com", "Gitee"),
    ("mybinder.org", "Binder"),
    ("kaggle.com", "Kaggle"),
    ("colab.research.google.com", "Colab"),
    ("code.google.com", "Google Code"),
    ("savannah.gnu.org", "Savannah"),
    ("git.io", "GitHub"),
)

# DOI URLs (doi.org/...) that resolve to a code / data archive, classified by
# a substring of the DOI path, so https://doi.org/10.5281/zenodo.123 is still
# caught as Zenodo.
DOI_PATH_HINTS: tuple[tuple[str, str], ...] = (
    ("zenodo", "Zenodo"),
    ("osf.io", "OSF"),
    ("dryad", "Dryad"),
    ("figshare", "Figshare"),
)

# ---------------------------------------------------------------------------
# Known data archives -> label
# ---------------------------------------------------------------------------
# Same shape and first-match-wins rule. What belongs here: a host that serves
# DATA you can go and download. What does not: a code forge (that is the
# table above), and a journal / preprint host (a paper is not a dataset).
DATA_HOST_LABELS: tuple[tuple[str, str], ...] = (
    ("openneuro.org", "OpenNeuro"),
    ("openfmri.org", "OpenfMRI"),
    ("neurovault.org", "NeuroVault"),
    ("dandiarchive.org", "DANDI"),
    ("brainlife.io", "brainlife"),
    ("fcon_1000.projects.nitrc.org", "INDI / FCP-1000"),
    ("nitrc.org", "NITRC"),
    ("crcns.org", "CRCNS"),
    ("physionet.org", "PhysioNet"),
    ("balsa.wustl.edu", "BALSA"),
    ("db.humanconnectome.org", "ConnectomeDB"),
    ("humanconnectome.org", "ConnectomeDB"),
    ("adni.loni.usc.edu", "ADNI / LONI"),
    ("ida.loni.usc.edu", "LONI IDA"),
    ("loni.usc.edu", "LONI"),
    ("nda.nih.gov", "NDA (NIMH)"),
    ("abcdstudy.org", "ABCD"),
    ("ukbiobank.ac.uk", "UK Biobank"),
    ("oasis-brains.org", "OASIS"),
    ("ppmi-info.org", "PPMI"),
    ("naturalscenesdataset.org", "NSD"),
    ("things-initiative.org", "THINGS"),
    ("cneuromod.ca", "CNeuroMod"),
    ("ebrains.eu", "EBRAINS"),
    ("gin.g-node.org", "G-Node GIN"),
    ("datalad.org", "DataLad"),
    ("academictorrents.com", "Academic Torrents"),
    ("data.mendeley.com", "Mendeley Data"),
    ("dataverse.harvard.edu", "Harvard Dataverse"),
    ("dataverse.org", "Dataverse"),
    ("synapse.org", "Synapse"),
    # Generalists: code AND data. Also in HOST_LABELS on purpose.
    ("osf.io", "OSF"),
    ("zenodo.org", "Zenodo"),
    ("datadryad.org", "Dryad"),
    ("dryad.org", "Dryad"),
    ("figshare.com", "Figshare"),
    ("huggingface.co", "Hugging Face"),
    ("kaggle.com", "Kaggle"),
)

# DOI URLs that resolve to a data archive -- so
# https://doi.org/10.18112/openneuro.ds002685.v1.0.1 is caught as OpenNeuro
# rather than read as just another paper DOI.
DATA_DOI_HINTS: tuple[tuple[str, str], ...] = (
    ("openneuro", "OpenNeuro"),
    ("18112", "OpenNeuro"),  # OpenNeuro's DOI prefix
    ("dandi", "DANDI"),
    ("zenodo", "Zenodo"),
    ("osf.io", "OSF"),
    ("dryad", "Dryad"),
    ("figshare", "Figshare"),
)

# ---------------------------------------------------------------------------
# URL machinery
# ---------------------------------------------------------------------------

# A URL with an explicit scheme or a leading www. ...
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'()\[\]{}]+")

# ... plus bare host/path mentions of the known hosts (`github.com/u/r` with no
# scheme, common in extracted text). Built FROM the host table so the two stay
# in sync, minus suffix-only hosts that are NEVER the registrable host
# (`github.io` is always `<user>.github.io` -- matching it bare would drop the
# subdomain and yield a broken URL; it's still classified for scheme'd URLs).
_BARE_ONLY_SUFFIXES = {"github.io"}

# Characters that are almost always sentence punctuation trailing a URL, not
# part of it. Stripped from each candidate's tail.
_TRAILING = ".,;:!?'\"”’)>]}»"


def build_bare_re(host_labels: tuple[tuple[str, str], ...]) -> re.Pattern[str]:
    """The bare-host regex for a (host, label) table."""
    return re.compile(
        r"(?i)\b(?:"
        + "|".join(re.escape(h) for h, _ in host_labels if h not in _BARE_ONLY_SUFFIXES)
        + r")/[^\s<>\"'()\[\]{}]+"
    )


Classifier = Callable[[str, str], "str | None"]


def make_classifier(host_labels: tuple[tuple[str, str], ...], doi_hints: tuple[tuple[str, str], ...]) -> Classifier:
    """The (host, path) -> label function for a host table. First match wins,
    which is why the tables order specific subdomains above the bare host."""

    def classify(host: str, path: str) -> str | None:
        host = (host or "").lower()
        if host.startswith("www."):
            host = host[4:]
        for suffix, label in host_labels:
            if host == suffix or host.endswith("." + suffix):
                return label
        if host == "doi.org" or host.endswith(".doi.org"):
            p = (path or "").lower()
            for hint, label in doi_hints:
                if hint in p:
                    return label
        return None

    return classify


_classify_code = make_classifier(HOST_LABELS, DOI_PATH_HINTS)
_CODE_BARE_RE = build_bare_re(HOST_LABELS)
_classify_data = make_classifier(DATA_HOST_LABELS, DATA_DOI_HINTS)
_DATA_BARE_RE = build_bare_re(DATA_HOST_LABELS)


def _clean_url(raw: str) -> str | None:
    """Trim trailing sentence punctuation and make a candidate fetchable
    (prepend https:// to bare-host / www. matches)."""
    u = (raw or "").strip().rstrip(_TRAILING)
    if not u:
        return None
    if not re.match(r"(?i)^https?://", u):
        u = "https://" + u.lstrip("/")
    return u


def dedup_key(url: str) -> str:
    """Canonical key for de-duping: drop the scheme, a leading www. and the
    trailing slash, so https://www.zenodo.org/x/ and zenodo.org/x collapse
    to one (the bare-host regex and the scheme regex can both match a link)."""
    k = re.sub(r"(?i)^https?://", "", (url or "").lower())
    if k.startswith("www."):
        k = k[4:]
    return k.rstrip("/")


def _is_plausible(url: str, path: str) -> bool:
    """Reject links that clearly aren't a real, reachable repo / record:
      - a bare host with no path (`https://github.com` -- no repo);
      - one STILL cut off at a hyphen after we tried to rejoin it across the
        line break (`.../kelseyhan-` with no continuation found).
    Better to drop a fragment than to surface a 404."""
    if _ends_truncated(url):
        return False
    return bool((path or "").strip("/"))


# Line-break repair. Extracted text routinely splits a long URL across two
# lines, so the captured token is cut off (`https://github.com/kelseyhan-`)
# and the rest (`lab/repo`) starts the next line. We rejoin them, but only on
# a HIGH-PRECISION "this link is truncated" signal so we never glue a COMPLETE
# url to the prose that happens to follow it.

# A run of URL-ish characters -- the continuation off the next line.
_URLCHARS_RE = re.compile(r"[^\s<>\"'()\[\]{}]+")
# The whitespace a line break leaves between a cut-off URL and its
# continuation: optional spaces, an optional single newline, optional spaces.
_BREAK_GAP_RE = re.compile(r"[ \t]*\n?[ \t]*")


def _ends_truncated(token: str) -> bool:
    """Does this URL token look CUT OFF mid-link? A real host / GitHub
    username / path segment never ends in a hyphen (GitHub forbids a trailing
    '-', and hyphenation drops one at the break), so a trailing '-' -- after
    stripping sentence punctuation -- is the tell."""
    return token.rstrip(_TRAILING).endswith("-")


def _host_only(token: str) -> bool:
    """True when the token is just a bare host with no path yet
    (`github.com/`, `https://osf.io`) -- the repo / record id went onto the
    next line. Unlike `github.com/owner/repo`, which already has a path."""
    t = re.sub(r"(?i)^https?://", "", token.rstrip(_TRAILING))
    _, _, rest = t.partition("/")
    return not rest.strip("/")


def _stitch(text: str, end: int, token: str) -> str:
    """Rejoin a URL split across a line break onto `token`, reading
    continuation run(s) off the following line(s). Fires only on a precise
    "cut off" signal:
      - the token ends in a hyphen -> rejoin across spaces OR a newline (the
        hyphen itself is the signal, so either gap is safe);
      - the token is a bare host with no path -> rejoin ONLY across a real
        newline (the path is on the next line), never across a lone space
        (which is far more likely just the next word).
    Capped at a few hops so a pathological input can't loop. The continuation
    fragment isn't itself a URL match, so it won't be double-yielded."""
    for _ in range(4):
        hyphen = _ends_truncated(token)
        hostonly = _host_only(token)
        if not (hyphen or hostonly):
            break
        gap = _BREAK_GAP_RE.match(text, end)
        if not gap or gap.end() == end:  # nothing split off
            break
        if hostonly and not hyphen and "\n" not in text[end:gap.end()]:
            break  # host-only needs a real line break
        cont = _URLCHARS_RE.match(text, gap.end())
        if not cont:
            break
        token, end = token + cont.group(0), cont.end()
    return token


def _iter_candidates(text: str, bare_re: re.Pattern[str]):
    """Raw URL-ish substrings of `text` (scheme / www. matches first, then
    bare known-host matches), each rejoined across line breaks. Overlaps are
    fine -- _clean_url normalizes and the caller de-dupes."""
    for rx in (_URL_RE, bare_re):
        for m in rx.finditer(text):
            yield _stitch(text, m.end(), m.group(0))


def extract_links_tagged(
    *labeled_texts: tuple[str, str], classify: Classifier = _classify_code, bare_re: re.Pattern[str] = _CODE_BARE_RE
) -> list[dict]:
    """Scan (where, text) pairs for links on a host table. A de-duped list,
    first-seen order, of {"url", "host", "where"}: host is the table's label
    ("GitHub"), where the label of the text the link was FIRST seen in."""
    seen: set[str] = set()
    links: list[dict] = []
    for where, text in labeled_texts:
        if not text:
            continue
        for raw in _iter_candidates(text, bare_re):
            url = _clean_url(raw)
            if not url:
                continue
            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            label = classify(parsed.netloc, parsed.path)
            if not label or not _is_plausible(url, parsed.path):
                continue
            key = dedup_key(url)
            if key in seen:
                continue
            seen.add(key)
            links.append({"url": url, "host": label, "where": where})
    return links


def code_links(*labeled_texts: tuple[str, str]) -> list[dict]:
    """Code-host links in (where, text) pairs: [{"url", "host", "where"}]."""
    return extract_links_tagged(*labeled_texts, classify=_classify_code, bare_re=_CODE_BARE_RE)


# OpenNeuro accessions are `ds` + exactly six digits, and papers cite them
# bare far more often than they link them ("the data are available on
# OpenNeuro (ds000105)"). Six digits glued to a leading `ds` is not a word, a
# year or a p-value, so we mint the record URL from it and mark the accession
# it came from.
_ACCESSION_RE = re.compile(r"(?i)\bds\d{6}\b")
_ACCESSION_URL = "https://openneuro.org/datasets/{acc}"


def _accession_links(*labeled_texts: tuple[str, str]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for where, text in labeled_texts:
        if not text:
            continue
        for m in _ACCESSION_RE.finditer(text):
            acc = m.group(0).lower()
            if acc in seen:
                continue
            seen.add(acc)
            out.append({"url": _ACCESSION_URL.format(acc=acc), "host": "OpenNeuro", "where": where, "accession": acc})
    return out


def data_links(*labeled_texts: tuple[str, str]) -> list[dict]:
    """Data-archive links in (where, text) pairs, then the bare OpenNeuro
    accessions the URL pass can't see. Same shape as code_links(); a minted
    link also carries "accession", so a page can say it was RECOVERED from an
    id rather than printed by the paper.

    An accession is a duplicate whenever it already appears ANYWHERE in a
    found link -- as the record path (openneuro.org/datasets/ds000105) or
    buried in a versioned DOI (doi.org/10.18112/openneuro.ds003020.v1.0.0) --
    so this is a substring test over the found URLs, not a key comparison.
    The real URL wins, since the URL pass runs first."""
    links = extract_links_tagged(*labeled_texts, classify=_classify_data, bare_re=_DATA_BARE_RE)
    found = " ".join(link["url"].lower() for link in links)
    for link in _accession_links(*labeled_texts):
        if link["accession"] not in found:
            links.append(link)
    return links


# ---------------------------------------------------------------------------
# Named datasets
# ---------------------------------------------------------------------------
# Most deep-learning fMRI papers never link their data: they say "we use HCP"
# and move on. Each name maps to the patterns that mention it.
DATASETS: dict[str, list[str]] = {
    "HCP (Human Connectome Project)": [r"\bHuman Connectome Project\b", r"\bHCP\b(?!-?MMP)", r"\bHCP-?(?:YA|1200|S1200|Aging|D)\b"],
    "NSD (Natural Scenes Dataset)": [r"\bNatural Scenes Dataset\b", r"\bNSD\b"],
    "ABIDE": [r"\bABIDE\s*(?:I{1,2}|1|2)?\b", r"\bAutism Brain Imaging Data Exchange\b"],
    "ADNI": [r"\bADNI\b", r"\bAlzheimer'?s Disease Neuroimaging Initiative\b"],
    "UK Biobank": [r"\bUK\s?Biobank\b", r"\bUKB\b"],
    "ADHD-200": [r"\bADHD-?200\b"],
    "Generic Object Decoding (Kamitani)": [r"\bGeneric Object Decoding\b", r"\bGOD dataset\b", r"\bDeepRecon\b", r"\bKamitani\b"],
    "BOLD5000": [r"\bBOLD5000\b"],
    "Narratives (Nastase)": [r"\bNarratives\b(?!\s+of)", r"\bNastase\b"],
    "Moth Radio Hour / Huth-LeBel story data": [r"\bMoth Radio Hour\b", r"\bLeBel\b", r"\bHuth\b"],
    "Pereira et al. 2018": [r"\bPereira\b"],
    "THINGS-fMRI": [r"\bTHINGS-?(?:fMRI|data)?\b"],
    "Algonauts": [r"\bAlgonauts\b"],
    "CNeuroMod / Courtois": [r"\bCNeuroMod\b", r"\bCourtois\b"],
    "StudyForrest": [r"\bStudy\s?Forrest\b"],
    "REST-meta-MDD": [r"\bREST-?meta-?MDD\b"],
    "OpenNeuro / ds00xxxx": [r"\bOpenNeuro\b", r"\bds\d{6}\b"],
    "SRPBS / Japanese multi-site": [r"\bSRPBS\b"],
    "ABCD": [r"\bABCD\b", r"\bAdolescent Brain Cognitive Development\b"],
    "MSC (Midnight Scan Club)": [r"\bMidnight Scan Club\b", r"\bMSC\b"],
    "Forrest Gump 7T": [r"\bForrest Gump\b"],
    "HCP-EP / HCP-D / HCP-A": [r"\bHCP-?(?:EP|D|A)\b"],
    "Deep Image Reconstruction (Shen)": [r"\bDeep Image Reconstruction\b"],
    "NOD (Natural Object Dataset)": [r"\bNatural Object Dataset\b", r"\bNOD\b"],
    "Nifty/Neuromark ICA templates": [r"\bNeuroMark\b"],
}
_DATASET_RES = {name: [re.compile(p) for p in pats] for name, pats in DATASETS.items()}

# Where each collection LIVES -- the page a reader would actually go to.
# Every URL was checked against the source itself, not remembered: the
# OpenNeuro accessions against OpenNeuro's API (ds001246 = "Generic Object
# Decoding (fMRI on ImageNet)", ds001506 = "Deep Image Reconstruction",
# ds002345 = "Narratives", ds000224 = "The Midnight Scan Club (MSC) dataset",
# ds003020 = the passive natural-language listening data, ds004496 = the
# large-scale naturalistic-scene data) and the OSF node against OSF's (crwz7 =
# "Toward a universal decoder of linguistic meaning from brain activation").
# A wrong link is worse than none, so check anything added the same way; a
# name with no entry simply renders unlinked.
HOMES: dict[str, str] = {
    "HCP (Human Connectome Project)": "https://www.humanconnectome.org/",
    "HCP-EP / HCP-D / HCP-A": "https://www.humanconnectome.org/",
    "NSD (Natural Scenes Dataset)": "https://naturalscenesdataset.org/",
    "ABIDE": "https://fcon_1000.projects.nitrc.org/indi/abide/",
    "ADHD-200": "https://fcon_1000.projects.nitrc.org/indi/adhd200/",
    "ADNI": "https://adni.loni.usc.edu/",
    "UK Biobank": "https://www.ukbiobank.ac.uk/",
    "ABCD": "https://abcdstudy.org/",
    "BOLD5000": "https://bold5000-dataset.github.io/website/",
    "THINGS-fMRI": "https://things-initiative.org/",
    "Algonauts": "http://algonauts.csail.mit.edu/",
    "CNeuroMod / Courtois": "https://www.cneuromod.ca/",
    "StudyForrest": "https://www.studyforrest.org/",
    "Forrest Gump 7T": "https://www.studyforrest.org/",
    "REST-meta-MDD": "http://rfmri.org/REST-meta-MDD",
    "SRPBS / Japanese multi-site": "https://bicr-resource.atr.jp/srpbsopen/",
    "OpenNeuro / ds00xxxx": "https://openneuro.org/",
    "Nifty/Neuromark ICA templates": "https://trendscenter.org/data/",
    "Generic Object Decoding (Kamitani)": "https://openneuro.org/datasets/ds001246",
    "Deep Image Reconstruction (Shen)": "https://openneuro.org/datasets/ds001506",
    "Narratives (Nastase)": "https://openneuro.org/datasets/ds002345",
    "MSC (Midnight Scan Club)": "https://openneuro.org/datasets/ds000224",
    "Moth Radio Hour / Huth-LeBel story data": "https://openneuro.org/datasets/ds003020",
    "NOD (Natural Object Dataset)": "https://openneuro.org/datasets/ds004496",
    "Pereira et al. 2018": "https://osf.io/crwz7/",
}

# What each collection IS, in one line. Deliberately WHAT and WHO, not how
# many: subject counts and scanner details drift between releases. A name with
# no entry simply shows no description.
DESCRIPTIONS: dict[str, str] = {
    "HCP (Human Connectome Project)": "Large-scale multimodal MRI of healthy young adults — the field's default resting-state and task reference.",
    "HCP-EP / HCP-D / HCP-A": "The Connectome lifespan and early-psychosis extensions — development, aging and clinical cohorts on HCP protocols.",
    "NSD (Natural Scenes Dataset)": "7T fMRI of eight subjects viewing tens of thousands of COCO images — the standard for image reconstruction work.",
    "ABIDE": "Aggregated resting-state fMRI from autism and control participants, pooled across many independent sites.",
    "ADHD-200": "Multi-site resting-state fMRI of children and adolescents with ADHD alongside typically-developing controls.",
    "ADNI": "Longitudinal MRI, PET, genetics and clinical follow-up on Alzheimer's disease and mild cognitive impairment.",
    "UK Biobank": "Population-scale UK cohort pairing brain MRI with genetics, health records and lifestyle measures.",
    "ABCD": "Longitudinal US study following adolescent brain development with repeated imaging and behavioural batteries.",
    "BOLD5000": "fMRI of subjects viewing 5,000 real-world scene images drawn from COCO, ImageNet and SUN.",
    "THINGS-fMRI": "Responses to the THINGS image database, which spans thousands of everyday object concepts.",
    "Algonauts": "A recurring challenge pairing brain responses to naturalistic images or video with model predictions.",
    "CNeuroMod / Courtois": "Deeply-sampled individuals scanned for many hours each on movies, video games and audio.",
    "StudyForrest": "Extensive 3T and 7T fMRI of participants hearing and watching the film Forrest Gump.",
    "Forrest Gump 7T": "The high-field arm of StudyForrest — 7T responses to the film's audio-visual narrative.",
    "REST-meta-MDD": "Aggregated resting-state fMRI from major-depression patients and controls across Chinese sites.",
    "SRPBS / Japanese multi-site": "Japanese multi-site resting-state fMRI spanning several psychiatric diagnoses and healthy controls.",
    "OpenNeuro / ds00xxxx": "The open BIDS archive itself — a paper citing a bare ds###### accession is pointing here.",
    "Nifty/Neuromark ICA templates": "TReNDS's spatially-constrained ICA templates, for extracting comparable networks across studies.",
    "Generic Object Decoding (Kamitani)": "fMRI while subjects viewed ImageNet objects — the classic object-decoding benchmark.",
    "Deep Image Reconstruction (Shen)": "Kamitani-lab fMRI of seen and imagined images, built for reconstructing what was viewed.",
    "Narratives (Nastase)": "A large collection of fMRI datasets in which subjects listened to spoken stories.",
    "MSC (Midnight Scan Club)": "Ten subjects scanned repeatedly across many sessions, for individual-level network mapping.",
    "Moth Radio Hour / Huth-LeBel story data": "Hours of fMRI per subject during passive listening to natural spoken stories.",
    "NOD (Natural Object Dataset)": "Large-scale fMRI of many subjects viewing naturalistic object images.",
    "Pereira et al. 2018": "fMRI of sentence and concept reading, built to train a general decoder of linguistic meaning.",
}


def home(name: str) -> str:
    """Where a detected dataset lives, or "" when we have no checked URL."""
    return HOMES.get(name, "")


def describe(name: str) -> str:
    """One line on what a detected dataset is, or "" when we have none."""
    return DESCRIPTIONS.get(name, "")


def detect(text: str, min_hits: int = 2) -> list[str]:
    """Which public datasets does this text name, in DATASETS order?

    min_hits is the bar for believing a mention. Two is right for a full
    paper -- 50,000 characters in which "HCP" turns up once in a sentence
    about somebody else's work is not a paper that uses HCP. It is wrong for
    an abstract on its own, which names its data once; pass 1 there."""
    if not text:
        return []
    return [name for name, rxs in _DATASET_RES.items() if sum(len(rx.findall(text)) for rx in rxs) >= min_hits]


def dataset_names(text: str, min_hits: int = 2) -> list[dict]:
    """Named public datasets in a paper's text: [{"name", "url",
    "description"}], sorted by name. The bibliography is cut HERE, always
    (callers pass the whole text): a reference list is a list of other
    papers' titles, and half of them name a dataset the paper never touched."""
    names = sorted(detect(sections.cut_bibliography(text or ""), min_hits=min_hits))
    return [{"name": n, "url": home(n), "description": describe(n)} for n in names]


# ---------------------------------------------------------------------------
# Per paper
# ---------------------------------------------------------------------------


def abstract_from_inverted(inv: dict | None) -> str:
    """Plain abstract text from OpenAlex's abstract_inverted_index
    ({word: [positions]})."""
    if not inv:
        return ""
    positions = sorted((pos, word) for word, poses in inv.items() for pos in poses)
    return " ".join(w for _, w in positions)


def scan_paper(title: str, abstract: str, body: str) -> dict:
    """Everything this module finds for one paper:
    {"code": [...], "data": [...], "names": [...]}.

    LINKS (code and data) read the abstract + the WHOLE extracted text, raw,
    bibliography included, as the old scan did: a URL is as likely to sit in a
    data-availability statement or a footnote as in the body, and the raw line
    breaks are what the split-URL repair needs. NAMES read the abstract + the
    text with its bibliography cut: a dataset name is a common short token and
    the reference list is full of them. With no body there are no names (an
    abstract alone is too thin for the two-mention bar). The title is not
    scanned for links (it never carries one); it is accepted so callers make
    one uniform call per paper."""
    texts = (("abstract", abstract or ""), ("body", body or ""))
    names = dataset_names(f"{abstract or ''}\n\n{body}") if (body or "").strip() else []
    return {"code": code_links(*texts), "data": data_links(*texts), "names": names}
