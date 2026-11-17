"""The review screener's state: the rules in use, the hand-checked overrides,
and the dataset consensus built from the screened papers.

Setups      named rule documents in db.BUCKET_REVIEW_RULES; one is in use.
            "default" is config/review.yaml, with the edits kept as a whole
            copy (key "rules") while there are any; Reset deletes the copy.
            Others ("setup:<id>") are whole documents an admin or an agent
            made, copied from a setup or written from scratch. Using another
            setup, or saving the one in use, moves the signature, so the
            content queue re-screens each candidate paper in turn -- or takes
            the result it kept for that signature (review@<sig>.json), so
            swapping back to a setup already run is instant.
Candidates  papers on any list or with a picked figure (main points
            candidates_fn at both). Only they are screened.
Consensus   each screened paper stores what acquisition values it states near
            each public dataset it names (review.json "mined"); the tally
            across papers is kept in memory and changed one paper at a time
            as its review finishes, never rebuilt from scratch per request.
Overrides   db.BUCKET_REVIEW_OVERRIDES, by paper key: applied when a result is
            read, so an override never re-runs anything.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import msgspec

from app.core import db
from app.review import rules as R
from app.review import screen

# The defaults that ship with the code: used when the config folder has no
# review.yaml of its own (a test's temporary config, an old install).
BUNDLED = Path(__file__).resolve().parents[2] / "config" / "review.yaml"
RULES_KEY = "rules"  # the default setup's edits
ACTIVE_KEY = "active"  # {"setup": id}: none is the default
SETUP_PREFIX = "setup:"
DEFAULT = "default"
DEFAULT_NAME = "Default"
MAX_SETUPS = 50
MAX_NAME = 80
MAX_DESCRIPTION = 2000
MAX_RULES_BYTES = 2_000_000
RESULT_FILE = "review.json"
STAGE = "review"
# Override keys that are not extraction fields but say something about the paper.
OVERRIDE_EXTRAS = ("Model_Name", "Decoding_Target", "Attention_Role", "Architecture_Summary", "Pipeline_Stages", "Input_Representation")


class SetupError(Exception):
    """A setup change refused: status and message as the routes send them."""

    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def _clean_description(text: str) -> str:
    text = str(text or "").strip()
    if len(text) > MAX_DESCRIPTION:
        raise SetupError(400, "review_setup_description_long")
    return text


def _check_size(data: dict[str, Any]) -> None:
    if len(msgspec.json.encode(data)) > MAX_RULES_BYTES:
        raise SetupError(400, "review_rules_too_large")


class ReviewService:
    def __init__(self, store: db.Store, defaults_path: Path, files: Any = None) -> None:
        self.store = store
        self.defaults_path = defaults_path if defaults_path.is_file() else BUNDLED
        self.files = files
        self._lock = threading.Lock()
        self._defaults: tuple[float, dict[str, Any]] | None = None
        self.problem = ""
        self.active = DEFAULT
        self._signatures: set[str] | None = None
        self.candidates_fn: Callable[[], set[str]] = lambda: set()
        self._candidates: set[str] | None = None
        self._tally: dict[str, dict[str, dict[str, list[str]]]] | None = None
        self._overrides: dict[str, dict[str, Any]] | None = None
        self.rules = self._load()

    # -- setups ----------------------------------------------------------------------

    def _record(self, setup: str) -> dict[str, Any] | None:
        """A named setup's record (never the default's)."""
        if setup == DEFAULT or not setup:
            return None
        record = self.store.get(db.BUCKET_REVIEW_RULES, SETUP_PREFIX + setup)
        return record if record and isinstance(record.get("rules"), dict) else None

    def _records(self) -> list[dict[str, Any]]:
        out = []
        for key, record in self.store.all(db.BUCKET_REVIEW_RULES):
            if str(key).startswith(SETUP_PREFIX) and isinstance(record, dict) and isinstance(record.get("rules"), dict):
                out.append(record)
        return sorted(out, key=lambda r: (str(r.get("name") or "").lower(), r.get("id") or ""))

    def active_id(self) -> str:
        record = self.store.get(db.BUCKET_REVIEW_RULES, ACTIVE_KEY) or {}
        setup = str(record.get("setup") or DEFAULT)
        return setup if setup == DEFAULT or self._record(setup) is not None else DEFAULT

    def exists(self, setup: str) -> bool:
        return setup == DEFAULT or self._record(setup) is not None

    def data_of(self, setup: str) -> dict[str, Any]:
        """A setup's rules document, as kept. SetupError 404 if there is none."""
        if setup == DEFAULT:
            record = self.edited()
            return record["rules"] if record else R.load(self.defaults()).data
        record = self._record(setup)
        if record is None:
            raise SetupError(404, "review_setup_not_found")
        return record["rules"]

    def compiled(self, setup: str) -> R.Rules:
        """A setup's rules, checked. RulesError if they no longer load."""
        if setup == self.active and not self.problem:
            return self.rules
        return R.load(self.data_of(setup))

    def signatures(self) -> set[str]:
        """Every setup's signature: the review results worth keeping. Worked
        out once per change to the setups (the queue asks per paper)."""
        with self._lock:
            if self._signatures is not None:
                return self._signatures
        found = {R.signature_of(self.data_of(DEFAULT)), self.signature}
        for record in self._records():
            try:
                found.add(R.signature_of(record["rules"]))
            except (TypeError, ValueError, msgspec.EncodeError):
                pass
        with self._lock:
            self._signatures = found
        return found

    def _setups_changed(self) -> None:
        with self._lock:
            self._signatures = None

    # -- rules -----------------------------------------------------------------------

    def _mtime(self) -> float:
        try:
            return self.defaults_path.stat().st_mtime
        except OSError:
            return 0.0

    def defaults(self) -> dict[str, Any]:
        mtime = self._mtime()
        if self._defaults is None or self._defaults[0] != mtime:
            self._defaults = (mtime, R.read_yaml(self.defaults_path))
        return self._defaults[1]

    def edited(self) -> dict[str, Any] | None:
        """The default setup's edits, or None (config/review.yaml as it is)."""
        record = self.store.get(db.BUCKET_REVIEW_RULES, RULES_KEY)
        return record if record and isinstance(record.get("rules"), dict) else None

    def _load(self) -> R.Rules:
        self.problem = ""
        self.active = self.active_id()
        if self.active != DEFAULT:
            record = self._record(self.active)
            try:
                return R.load(record["rules"])  # type: ignore[index]
            except R.RulesError as error:
                self.problem = f"The setup in use ({record.get('name') if record else self.active}) no longer loads ({error}); the default rules are in use until it is fixed."
                self.active = DEFAULT
        record = self.edited()
        if record is not None:
            try:
                return R.load(record["rules"])
            except R.RulesError as error:
                # Saved rules the code no longer accepts (a newer default added
                # a threshold): run on the defaults and say so on the page.
                self.problem = f"Your saved rules no longer load ({error}); the defaults are in use until you save again."
        return R.load(self.defaults())

    def refresh(self) -> bool:
        """Pick up an edited config/review.yaml when the default setup is in
        use and has no edited copy. -> whether the rules changed."""
        if self.active != DEFAULT or self.edited() is not None:
            return False
        with self._lock:
            before = self.rules.signature
            try:
                self.rules = R.load(self.defaults())
            except (R.RulesError, OSError) as error:
                self.problem = f"config/review.yaml does not load: {error}"
                return False
            return self.rules.signature != before

    @property
    def signature(self) -> str:
        return self.rules.signature

    def _keep(self, setup: str, compiled: R.Rules) -> None:
        self._setups_changed()
        if setup == self.active:
            with self._lock:
                self.rules = compiled
                self.problem = ""

    def save(self, data: dict[str, Any], by: str) -> R.Rules:
        """The default setup's rules. Raises RulesError, saving nothing, when
        they do not load."""
        return self.save_setup(DEFAULT, by, rules=data)

    def save_setup(self, setup: str, by: str, rules: dict[str, Any] | None = None, changes: list[dict[str, Any]] | None = None,
                   name: str | None = None, description: str | None = None, base_signature: str = "") -> R.Rules:
        """Change a setup: its whole rules, or changes to them (paths as
        R.CHANGE_PATHS), and for a named one its name and description.
        RulesError or SetupError, saving nothing, when it cannot."""
        current = self.data_of(setup)
        if base_signature and base_signature != R.signature_of(current):
            raise SetupError(409, "review_rules_moved", signature=R.signature_of(current))
        if rules is not None and changes:
            raise SetupError(400, "review_rules_or_changes")
        data = rules if rules is not None else R.apply_changes(current, changes) if changes else current
        compiled = R.load(data)
        _check_size(compiled.data)
        now = time.time()
        if setup == DEFAULT:
            if (name is not None and name.strip() != DEFAULT_NAME) or (description is not None and description.strip()):
                raise SetupError(409, "review_default_fixed")
            if compiled.signature == R.load(self.defaults()).signature:
                # Saved back to exactly the defaults: no copy needed.
                self.store.delete(db.BUCKET_REVIEW_RULES, RULES_KEY)
            else:
                self.store.put(db.BUCKET_REVIEW_RULES, RULES_KEY, {"rules": compiled.data, "updated_at": now, "updated_by": by})
        else:
            record = dict(self._record(setup) or {})
            if name is not None:
                record["name"] = self._check_name(name, setup)
            if description is not None:
                record["description"] = _clean_description(description)
            record.update({"rules": compiled.data, "updated_at": now, "updated_by": by})
            self.store.put(db.BUCKET_REVIEW_RULES, SETUP_PREFIX + setup, record)
        self._keep(setup, compiled)
        return compiled

    def _check_name(self, name: str, setup: str = "") -> str:
        name = " ".join(str(name).split())
        if not name:
            raise SetupError(400, "review_setup_name_missing")
        if len(name) > MAX_NAME:
            raise SetupError(400, "review_setup_name_long")
        taken = {DEFAULT_NAME.lower()} | {str(r.get("name") or "").lower() for r in self._records() if r.get("id") != setup}
        if name.lower() in taken:
            raise SetupError(409, "review_setup_name_taken")
        return name

    def create(self, name: str, by: str, description: str = "", source: str = DEFAULT, rules: dict[str, Any] | None = None) -> str:
        """A new named setup: a copy of another setup's rules, or the rules
        given. -> its id."""
        if len(self._records()) >= MAX_SETUPS:
            raise SetupError(409, "review_setups_full")
        name = self._check_name(name)
        if rules is None:
            if not self.exists(source):
                raise SetupError(404, "review_setup_not_found")
            rules = self.data_of(source)
        compiled = R.load(rules)
        _check_size(compiled.data)
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-") or "setup"
        setup, n = base, 1
        while setup == DEFAULT or self._record(setup) is not None:
            n += 1
            setup = f"{base}-{n}"
        now = time.time()
        self.store.put(db.BUCKET_REVIEW_RULES, SETUP_PREFIX + setup, {
            "id": setup, "name": name, "description": _clean_description(description), "rules": compiled.data,
            "based_on": source, "created_at": now, "created_by": by, "updated_at": now, "updated_by": by,
        })
        self._setups_changed()
        return setup

    def activate(self, setup: str) -> R.Rules:
        """Use a setup from now on. RulesError if its rules no longer load."""
        compiled = R.load(self.data_of(setup))
        if setup == DEFAULT:
            self.store.delete(db.BUCKET_REVIEW_RULES, ACTIVE_KEY)
        else:
            self.store.put(db.BUCKET_REVIEW_RULES, ACTIVE_KEY, {"setup": setup, "at": time.time()})
        with self._lock:
            self.active = setup
            self.rules = compiled
            self.problem = ""
            self._signatures = None
        return compiled

    def delete(self, setup: str) -> None:
        if setup == DEFAULT:
            raise SetupError(409, "review_default_kept")
        if self._record(setup) is None:
            raise SetupError(404, "review_setup_not_found")
        if setup == self.active:
            raise SetupError(409, "review_setup_in_use")
        self.store.delete(db.BUCKET_REVIEW_RULES, SETUP_PREFIX + setup)
        self._setups_changed()

    def reset(self, setup: str = DEFAULT) -> R.Rules:
        """The default setup back to config/review.yaml."""
        if setup != DEFAULT:
            raise SetupError(409, "review_reset_default_only")
        self.store.delete(db.BUCKET_REVIEW_RULES, RULES_KEY)
        compiled = R.load(self.defaults())
        self._keep(DEFAULT, compiled)
        return compiled

    def _summary(self, setup: str, record: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
        data = self.data_of(setup)
        problem = ""
        try:
            R.load(data)
        except R.RulesError as error:
            problem = str(error)
        if setup == DEFAULT:
            edited = self.edited() or {}
            meta = {"name": DEFAULT_NAME, "description": "", "based_on": "", "builtin": True, "edited": bool(edited),
                    "updated_at": edited.get("updated_at"), "updated_by": edited.get("updated_by", "")}
        else:
            record = record or {}
            meta = {"name": record.get("name") or setup, "description": record.get("description") or "", "based_on": record.get("based_on") or "",
                    "builtin": False, "edited": True, "updated_at": record.get("updated_at"), "updated_by": record.get("updated_by", "")}
        return {
            "id": setup, **meta, "active": setup == self.active, "signature": R.signature_of(data),
            "changed_count": len(R.differences(data, defaults)), "problem": problem,
        }

    def setups(self) -> list[dict[str, Any]]:
        """Every setup, the default first."""
        defaults = R.load(self.defaults()).data
        out = [self._summary(DEFAULT, None, defaults)]
        out += [self._summary(str(r.get("id")), r, defaults) for r in self._records()]
        return out

    def view(self, setup: str) -> dict[str, Any]:
        """One setup as the Screener rules page loads it."""
        defaults = R.load(self.defaults()).data
        record = self._record(setup)
        if setup != DEFAULT and record is None:
            raise SetupError(404, "review_setup_not_found")
        summary = self._summary(setup, record, defaults)
        data = self.data_of(setup)
        problem = summary["problem"] or (self.problem if setup == DEFAULT and self.active == DEFAULT else "")
        return {
            "setup": summary,
            "rules": data,
            "defaults": defaults,
            "changed": R.differences(data, defaults),
            "signature": summary["signature"],
            "in_use": self.active,
            "in_use_signature": self.signature,
            "edited": summary["edited"],
            "updated_at": summary["updated_at"],
            "updated_by": summary["updated_by"],
            "problem": problem or (self.problem if summary["active"] else ""),
            "post_kinds": list(R.POST_KINDS),
            "groups": list(R.GROUPS),
            "params": list(R.PARAMS),
            "vocab_names": list(R.VOCAB_NAMES),
        }

    def snapshot(self) -> dict[str, Any]:
        """The setup in use, as the page loads it."""
        return self.view(self.active)

    # -- candidates ---------------------------------------------------------------------

    def candidates(self) -> set[str]:
        with self._lock:
            if self._candidates is not None:
                return self._candidates
        found = set(self.candidates_fn())
        with self._lock:
            self._candidates = found
        return found

    def candidates_changed(self) -> None:
        with self._lock:
            self._candidates = None

    def stale_count(self, compiled: R.Rules | None = None) -> int:
        """How many candidates a save of these rules would re-screen."""
        if compiled is not None and compiled.signature == self.signature:
            return 0
        return len(self.candidates())

    # -- screening -------------------------------------------------------------------------

    def screen(self, title: str, abstract: str, methods: str, body: str, rules: R.Rules | None = None) -> dict[str, Any]:
        return screen.screen_paper(rules or self.rules, title, abstract, methods, body)

    def screened(self, key: str, result: dict[str, Any]) -> None:
        """A paper's review finished: its part of the consensus moves."""
        with self._lock:
            if self._tally is not None:
                if result.get("mined"):
                    self._tally[key] = result["mined"]
                else:
                    self._tally.pop(key, None)

    def dropped(self, key: str) -> None:
        with self._lock:
            if self._tally is not None:
                self._tally.pop(key, None)

    # -- the dataset consensus --------------------------------------------------------------

    def _load_tally(self) -> dict[str, dict[str, dict[str, list[str]]]]:
        with self._lock:
            if self._tally is not None:
                return self._tally
        tally: dict[str, dict[str, dict[str, list[str]]]] = {}
        if self.files is not None:
            for key, stages in self.files.summaries().items():
                if stages.get(STAGE, ("",))[0] != "done":
                    continue
                result = self.files.read(key, RESULT_FILE) or {}
                if result.get("mined"):
                    tally[key] = result["mined"]
        with self._lock:
            if self._tally is None:
                self._tally = tally
            return self._tally

    def consensus(self) -> list[dict[str, Any]]:
        """One row per (dataset, parameter) with a value at least min_papers
        papers report: {dataset, parameter, value, n, others: [{value, n}],
        sources: [keys]}."""
        tally = self._load_tally()
        rules = self.rules
        by: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        with self._lock:
            items = list(tally.items())
        for key, mined in items:
            for ds, params in mined.items():
                for param, values in params.items():
                    for value in values:
                        by[ds][param][value].add(key)
        min_papers = rules.cons("min_papers")
        top_k = int(rules.cons("top_k"))
        rows = []
        for ds in sorted(by):
            for param in R.PARAMS:
                values = by[ds].get(param)
                if not values:
                    continue
                ranked = sorted(values.items(), key=lambda kv: (-len(kv[1]), kv[0]))
                ranked = [(v, ks) for v, ks in ranked if len(ks) >= min_papers][:top_k]
                if not ranked:
                    continue
                best, keys = ranked[0]
                rows.append({
                    "dataset": ds, "parameter": param, "value": best, "n": len(keys),
                    "others": [{"value": v, "n": len(k)} for v, k in ranked[1:]], "sources": sorted(keys)[:4],
                })
        return rows

    # -- overrides --------------------------------------------------------------------------

    def overrides(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._overrides is not None:
                return self._overrides
        found = {str(k): v.get("fields") or {} for k, v in self.store.all(db.BUCKET_REVIEW_OVERRIDES)}
        with self._lock:
            self._overrides = found
        return found

    def set_override(self, key: str, fields: dict[str, str], by: str) -> None:
        fields = {k: str(v).strip() for k, v in fields.items() if str(v).strip()}
        if fields:
            self.store.put(db.BUCKET_REVIEW_OVERRIDES, key, {"fields": fields, "updated_at": time.time(), "updated_by": by})
        else:
            self.store.delete(db.BUCKET_REVIEW_OVERRIDES, key)
        with self._lock:
            self._overrides = None

    def import_overrides(self, data: dict[str, Any], by: str = "import-legacy") -> int:
        """The old config/review-overrides.json: {paper key: {field: value}},
        "_" keys being notes. An override already here is kept."""
        have = self.overrides()
        n = 0
        with self.store.transaction() as tx:
            for key, fields in data.items():
                if key.startswith("_") or not isinstance(fields, dict) or key in have:
                    continue
                clean = {k: str(v) for k, v in fields.items() if isinstance(k, str) and str(v).strip()}
                if clean:
                    tx.put(db.BUCKET_REVIEW_OVERRIDES, key, {"fields": clean, "updated_at": time.time(), "updated_by": by})
                    n += 1
        with self._lock:
            self._overrides = None
        return n

    def override_for(self, key: str, doi: str = "") -> dict[str, Any]:
        found = self.overrides()
        return found.get(key) or (found.get(doi.lower()) if doi else None) or {}

    # -- reading a paper's review --------------------------------------------------------------

    def result(self, key: str, doi: str = "") -> dict[str, Any] | None:
        """A paper's review as the screens show it: the stored result with
        overrides applied and acquisition blanks filled from the dataset
        consensus (marked so). None if it was never screened."""
        if self.files is None:
            return None
        stored = self.files.read(key, RESULT_FILE)
        if not stored:
            return None
        return self.present(stored, self.override_for(key, doi), self.consensus())

    def present(self, stored: dict[str, Any], override: dict[str, Any], consensus: list[dict[str, Any]], rules: R.Rules | None = None) -> dict[str, Any]:
        rules = rules or self.rules
        index = {(r["dataset"], r["parameter"]): (r["value"], r["n"]) for r in consensus}
        fallback = rules.doc.consensus.fallback
        quotes = int(rules.ext("evidence_quotes"))
        used = stored.get("datasets") or []
        fields_out: dict[str, Any] = {}
        found = stored.get("fields") or {}
        for spec in rules.fields:
            got = found.get(spec.name) or {}
            values = list(got.get("values") or [])
            entry: dict[str, Any] = {
                "group": spec.group, "value": values[0] if values else "", "values": values,
                "counts": got.get("counts") or {}, "evidence": [got["evidence"][v] for v in values[:quotes] if v in (got.get("evidence") or {})],
                "source": "auto" if values else "absent",
            }
            if got.get("dropped"):
                entry["dropped"] = got["dropped"]
            if override.get(spec.name):
                entry.update({"value": override[spec.name], "values": [override[spec.name]], "counts": {}, "source": "curated"})
            elif not values and spec.name in fallback:
                param = fallback[spec.name]
                hits = [(ds, *index[(ds, param)]) for ds in used if (ds, param) in index]
                if len(hits) == 1:
                    ds, value, n = hits[0]
                    entry.update({"value": value, "values": [value], "source": "dataset", "from_dataset": ds, "dataset_papers": n})
                elif len(hits) > 1:
                    entry["note"] = "several datasets: see the dataset consensus"
            fields_out[spec.name] = entry
        verdict = dict(stored.get("verdict") or {})
        if override.get("Attention_Role"):
            verdict["attention_role"] = override["Attention_Role"]
        return {
            "rules": stored.get("rules"),
            "current": stored.get("rules") == rules.signature,
            "mode": stored.get("mode", "full"),
            "verdict": verdict,
            "fields": fields_out,
            "datasets": used,
            "model_name": override.get("Model_Name") or stored.get("model_name") or "",
            "curated": bool(override),
            "override": override,
            "notes": {k: override[k] for k in OVERRIDE_EXTRAS if override.get(k)},
        }
