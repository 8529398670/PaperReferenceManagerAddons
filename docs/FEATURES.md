# Features: the old prma, and where each one lands here

Every feature of the old app (`~/WORKSPACE/PYTHON/PaperReferenceManagerAddons`). `[x]` is done here; the tag says which phase it belongs to. Ticked off as each lands.

The idea that changes everything: **no reindex, no pipeline to run**.
- Zotero is the catalogue: a paper saved there shows up here within seconds.
- Full text comes from Zotero's own PDF extraction (`.zotero-ft-cache`).
- Search is updated one paper at a time.
- Everything derived from a paper (citation network, methods, code and dataset links, figures) fills in by itself when it is ready, and shows as pending until then.

## A. Library and lookup
- [x] **P1** Zotero library read live: copied safely while Zotero is open, and watched every 2 s.
- [x] **P1** DOI / key normalisation as the old app did it (`nodoi-zotero-*` keys), so old lists still match.
- [x] **P1** `/api/exists` + `/api/version` for the userscripts (a DOI settles it; with no DOI, title fuzzy ≥ 96). An API key is required.
- [x] **P1** Userscripts updated (`userscripts/`): new address, `Authorization: Bearer`.
- [x] **P1** PDF served from Zotero storage (`/api/paper/pdf?key=`).
- [ ] **P2** "Recently added" from Zotero, on the Lists screen.
- [ ] **P4** Paper screen: abstract, full text, methods, links, content status.
- [ ] **P7** Research-log check (`check-missing-file`).

## B. Search and the missing pool
- [x] **P1** Folded text (accents and punctuation flattened), with the boolean grammar: AND, OR, NOT, `-term`, `"phrase"`.
- [x] **P1** Relevance ranking with the old title boosts; the closest titles when nothing matches.
- [x] **P1** Title-mode fuzzy search (typos, a pasted DOI).
- [x] **P1** Full text searchable, updated per paper (FTS5). No reindex.
- [ ] **P4** Missing pool: in bibliographies, newer citing, all missing; top authors.
- [ ] **P4** Tiered multi-column sort, skip/unskip, Read section view.
- [ ] **P4** OpenAlex fetched per paper, lazily, with a cache. Seeded from the old cache.

## C. Lists (the old /sort)
- [x] **P1** Lists: create, pick, numbered rows.
- [x] **P1** Type a number to move a row; drag by the grip.
- [x] **P1** Search to add (title fuzzy, or a DOI); "on the list at #n" shown.
- [x] **P1** Tags: add and remove, pastel colours (the old palette), autocomplete.
- [x] **P1** Notes column; remove a row.
- [x] **P1** Undo/redo for every change (Ctrl+Z / Ctrl+Y), with an undo toast for removals.
- [x] **P1** Live: other tabs, other people and agents' changes appear without a reload.
- [x] **P1** The full ops engine ported (`app/boards/ops.py`): about 30 ops, `dry_run`, `if_rev`, `#N`, positions.
- [x] **P1** Ops over the API (`POST /api/lists/<slug>/ops`, `GET /api/lists/schema`).
- [x] **P1** Ops over MCP (`search_library`, `list_lists`, `get_list`, `list_schema`, `list_ops`).
- [x] **P1** Old lists imported: `manage import-legacy --from <old output>`.
- [x] **P1** Every change keeps the previous version (the last 40 per list).
- [ ] **P2** Columns: add, rename, move, delete, fold, resize; live links in cells.
- [ ] **P2** Multi-select, bulk tagging, tag filter any/all/none, find a tag, chip bar drag order, Colours dialog.
- [ ] **P2** Order-by once, Auto-move, jump to # / anchor.
- [ ] **P2** Staging shelf + Import refs (paste, .docx/.txt; AMA/Vancouver/APA/IEEE).
- [ ] **P2** CSV import/export with `Cite`.
- [ ] **P2** CSL citations (in-text + full, copy buttons, style picker).
- [ ] **P2** Version history screen with restore; view-only lock in the list menu.
- [ ] **P2** Faster redraw of very long lists (only changed rows).
- [ ] **P3** Duplicate, rename (with redirect), delete (to trash, undoable).
- [ ] **P3** Copy/move rows to another list; import from lists or remaining papers.
- [ ] **P3** Tags and cells mirrored across lists (two-way / one-way / off).
- [ ] **P3** Public Google Sheet import with cell links and the per-column merge dialog.
- [ ] **P7** Google Sheets live two-way mirror.

## D. Tiers
- [ ] **P3** A tier board as a list with sections: label, description, colour, target, reorder, delete.
- [ ] **P3** Rank within a tier, move across tiers.
- [ ] **P3** Modality bar; legacy `tiers.json` import; `pull_tiers`.

## E. Per-paper content (lazy, no pipeline to run)
- [ ] **P4** Per-paper queue: new paper, changed PDF, or opened-and-not-ready, each enqueue it.
- [ ] **P4** Light stages in the server: OpenAlex, modality tags, methods split, code and dataset links.
- [ ] **P4** Status / Errors screen (the queue and its failures).
- [ ] **P5** Optional worker (`python -m app worker`): YOLO figure crops + montage, OCR for scanned PDFs.
- [ ] **P5** GitHub / OSF enrichment, repair of OCR-mangled repo links, dataset descriptions.
- [ ] **P7** LLM summaries + rollup.

## F. Code and Datasets screens
- [ ] **P5** Membership columns (Review / List / Tier / Figs), host filters, xlsx/CSV export, by-dataset view.

## G. Figures
- [ ] **P5** All figures / method-matched: pick and skip, chips, keyboard stepping, export. Old picks imported.

## H. Review
- [ ] **P6** Three-criteria screen, about 50 fields with evidence quotes, plausibility gates, dataset consensus, overrides, excluded/borderline papers, export. Run per paper, not as a rebuild.
- [ ] **P6** Missing-pool variant with calibration and near misses (same screen, a pool switch).

## I. Extras
- [ ] **P7** `missing.xlsx`, crawl, saved searches.

## J. Accounts and running it (the template)
- [x] **P1** Login links, users, roles, API keys, sessions, two-factor, activity log, jobs, settings, backups, maintenance, MCP.

## Left behind on purpose
- `snapshot`, `reindex`, `process`, `reprocess`: nothing to run any more.
- Mendeley: Zotero only.
- The TUI and `--exists` minimal mode.
- Anonymous read-only viewing: everything needs sign-in, and the userscripts use an API key.
- The hidden hold-a-key gestures, the "skin" switch, and the `file://` figure reports.
- The hard-coded WSU proxy: it is `library.proxy_url` in config.yaml now.
