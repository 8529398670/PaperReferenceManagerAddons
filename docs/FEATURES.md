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
- [x] **P2** "Recently added" from Zotero, on the Lists screen (past week / 2 weeks / month, multi-pick, tag and position per paper).
- [x] **P4** Paper screen (`#paper/<key>`, every title links there): abstract (Zotero, else OpenAlex), the text split on its headings with a table of contents, code and dataset links, citations with a link to its missing network, which lists it is on, each stage's state with Retry, Prev / Next through the list it was opened from.
- [ ] **P7** Research-log check (`check-missing-file`).

## B. Search and the missing pool
- [x] **P1** Folded text (accents and punctuation flattened), with the boolean grammar: AND, OR, NOT, `-term`, `"phrase"`.
- [x] **P1** Relevance ranking with the old title boosts; the closest titles when nothing matches.
- [x] **P1** Title-mode fuzzy search (typos, a pasted DOI).
- [x] **P1** Full text searchable, updated per paper (FTS5). No reindex.
- [x] **P4** Missing pool (`search.db`, filled one paper at a time as its OpenAlex record lands, counters kept, deduplicated against the library by OpenAlex id, DOI or title): All missing, In bibliographies, Newer / citing, top 100 authors.
- [x] **P4** Missing screen: the library's boolean search, tiered multi-column sort (ranks shown), Load more, skip / unskip (undoable, Show skipped, old `skipped.json` imported), Add to list with the work's WID, DOI and OA PDF, one paper's network (`#missing/<key>`). Read section view is the Paper screen's text.
- [x] **P4** OpenAlex fetched per paper (meta, references in batches of 50, every page of citers; 429 waited out, 404 cached as not found). Seeded from the old cache: `manage import-legacy --openalex --from <old output>`.

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
- [x] **P2** Every op usable and tested; read routes `GET /api/lists/<slug>/rows` and `/export.csv`; MCP `list_history`.
- [x] **P1** Old lists imported: `manage import-legacy --from <old output>`.
- [x] **P1** Every change keeps the previous version (the last 40 per list).
- [x] **P2** Columns: add, rename, move, delete, fold, resize; live links in cells.
- [x] **P2** Multi-select, bulk tagging, painting, tag filter any/all/none, find a tag, chip bar drag order, Colours dialog.
- [x] **P2** Order-by once, Auto-move, Add-to, jump to # / anchor / top / bottom.
- [x] **P2** Staging shelf + Import refs (paste, .docx/.txt; AMA/Vancouver/APA/IEEE).
- [x] **P2** CSV import (merge / replace, one undo step) and export with `Cite` (all rows, or the rows shown).
- [x] **P2** CSL citations (in-text + full, copy buttons, style picker; `POST /api/cite`).
- [x] **P2** Version history with a preview of what restoring changes, and restore (undoable); view-only lock in the list menu, live in every tab.
- [x] **P2** Faster redraw of very long lists (only changed rows; ~0.65 s → ~0.1 s on 1,527 rows), and focus kept across redraws.
- [x] **P3** Duplicate, rename (the old slug keeps answering), delete (to the trash for 30 days, undoable; Deleted lists to put one back; ops on it answer 410); undoable list creation; `#lists/<slug>` links.
- [x] **P3** Copy/move rows to another list (or a new one; top, bottom or #N; undo covers both lists); import from lists or Remaining papers with filters, a pick table and positions (`GET /api/lists/<slug>/remaining`).
- [x] **P3** Tags and cells mirrored across lists (two-way / one-way / off, in the list menu); papers arriving on a list filled from the sharing lists; locked lists skipped; restores travel too.
- [x] **P3** Public Google Sheet import (`POST /api/sheet/csv`, docs.google.com only) with cell links and the per-column merge dialog (fill / overwrite / leave out, tags add / replace, keep or take the sheet's order; add only; one undo step). A downloaded CSV goes through the same dialog.
- [ ] **P7** Google Sheets live two-way mirror.

## D. Tiers
- [x] **P3** A tier board as a list with sections (Tiers… in the list menu): label, description, colour, target (◉), reorder, delete (rows to Unranked), switch on and off.
- [x] **P3** Rank within a tier (type it), move across tiers (drag onto a row or a tier heading, or the tier picker on each row); CSV export/import carries a Tier column.
- [x] **P3** Legacy `tiers.json` (+ lock) imported as a tier board "Tiers"; `pull_tiers` from any tier board.
- [ ] **P4** Modality bar (modalities are tags; their own chip group needs the modality vocabulary from P4). The vocabulary is in now (`config/modalities.yaml`), and new rows are auto-tagged from it; the separate chip group is not drawn yet.

## E. Per-paper content (lazy, no pipeline to run)
- [x] **P4** Per-paper queue (`<app dir>/papers/content.db`): a new paper, a changed PDF or text (path, mtime, size), or an edited modality vocabulary each queue just the stages that read it; opening a paper puts it first; failures back off and never block others.
- [x] **P4** Light stages in the server, two lanes (network, local text): OpenAlex, methods split, code links, dataset links and named datasets, modality tags. Badges on Library and list rows fill in live; Library filter chips: Code, Data, No PDF text, OpenAlex missing.
- [x] **P4** Status screen: a card per stage with counts and a bar, live; per stage the papers still to do or failed (why, first / last failed, tries), search, sort, Retry one or all.
- [x] **P5** Optional worker (`python -m app worker`, started by `scripts/run.sh worker` in its own `.venv-worker` from `requirements-pipeline.txt`): doclayout-yolo figure crops at 400 DPI with their captions, numbered as the old app did, and a montage; RapidOCR for a PDF whose text is missing or unusable, which then feeds search and the text stages. It claims tasks from the same queue with a lease and checks in every 20 s; the Status screen shows it. With no worker, figures and OCR read "not available" and nothing else waits. `manage import-legacy --figures --from <old output>` links the old crops, montages and picks in.
- [x] **P5** GitHub / OSF enrichment (`enrich.github_token`, `enrich.osf_token`; without a token that host is not asked): each unique repo's metadata and README, OSF nodes and their wiki, method tags confirmed (README) or inferred (the linking papers' modality tags), OCR-mangled GitHub links repaired against the owner's repos (exact / prefix / fuzzy, with the original kept), archive records described (Zenodo, Figshare, OpenNeuro, OSF, else the page title). The old caches are converted, not refetched.
- [ ] **P7** LLM summaries + rollup.

## F. Code and Datasets screens
- [x] **P5** Code screen: one row per paper with code; repositories with what GitHub / OSF say, methods ✓ / ·, repaired links; Lists, Tier and Figs columns; host and membership filters, text search; sortable; .xlsx (papers + links) and CSV of exactly what is shown.
- [x] **P5** Datasets screen: by dataset (what it is, papers using it with the roll call, on lists, in tiers, years) and by paper (records linked, ˟ for accessions recovered from a bare ds######, named collections, code count); filters for linked / named-only, code, membership, archive; .xlsx and CSV.
- [x] **P6** The Review column (included / borderline / excluded / waiting, linked to the Review screen) and the "In the review" filter on Code and Datasets, updated live as papers are screened.

## G. Figures
- [x] **P5** Figures screen: All figures / Method figures (captions matched against `config/method-images.txt`, threshold 85, three weak hits); pick in pick order, skip (Space), arrow keys between papers; chips (All, Overview, Picked, Picked in the other view, Skipped), modality and keyword filters; sort by added, published, best match, most figures, title; picks as JSON / CSV; Clear (undoable). Papers load as the grid scrolls and images only near the screen (thumbnails made on first view). Old picks imported.

## H. Review
- [x] **P6** Screener, run per paper (`app/review/`): a `review` stage in the content queue for every paper on a list or with a picked figure, screened against the three criteria (fMRI dominant, decodes, attention in the authors' own model) with a "why" per test (counts against each bar, the words that matched); 52 extracted fields, each value with the sentence it came from, plausibility gates, most-stated first; datasets named and the acquisition values stated near them, tallied into a dataset consensus one paper at a time; borderline flag; hand-checked overrides (`db` bucket, `manage import-legacy` brings `config/review-overrides.json`) applied when read. Same answers as the old screener on a hundred library papers (`app/tests/test_review.py` compares when the old repo is on the machine).
- [x] **P6** Screener rules page (admins, `#review-rules`): every word list, threshold (with what it does and its default), task category and priority, exclusion, extraction field (patterns, how the value is made, plausible range), dataset and consensus setting is shown and editable; each edit is checked as you type and a bad pattern is marked where it is; Try it screens a library paper or pasted text with the unsaved rules beside the saved ones; Save re-screens the candidates in the background (progress on the page); Reset to defaults; Export YAML. Defaults in `config/review.yaml`, edits in the database.
- [x] **P6** Screener rule setups on the API and MCP (admins and admin API keys): named setups beside the default (copy one, or write one from scratch), switched with Use this setup; each paper keeps its result per setup (`review@<sig>.json`), so switching back to a setup already run is instant. Agents edit by change paths (`extraction.fields[TR].patterns[+]`) and read `screener_rules_guide` for the document's schema. Tools: `list_screener_setups`, `get_screener_setup`, `create_screener_setup`, `save_screener_setup`, `use_screener_setup`, `delete_screener_setup`, `reset_screener_setup`, `check_screener_rules`, `test_screener`, `screener_progress`, `screener_rules_guide`, `list_review_overrides`, `set_review_override`.
- [x] **P6** Review screen (`#review`, `static/js/review.js`, `GET /api/review/library`, `/api/review/paper`; MCP `list_review`, `get_review`): counts (included / borderline / excluded, waiting, under old rules), the criteria (collapsible); filters for priority, task category, on a list, figure picks, hand-checked, ships code, text; sort by priority then newest, recently added, publication date, year, citations, title, model name (reversible, papers without the key last); paper cards with the link strip and Figures (montage), Details opening the why and every field by group, a value clicked showing its quote and the other values stated, "from dataset" values marked with how many papers back them, blanks "not stated"; Borderline only; the excluded table with the tests each failed; the dataset consensus table; JSON / CSV of the cards shown, in their order. Live: no build, the page reloads as papers are screened.
- [x] **P6** Missing pool on the same screen (`#review/missing`, `GET /api/review/missing`, `/api/review/missing/work`; MCP `list_review_missing`, `get_review_missing_work`): every work in the pool screened on its title and abstract (abstract thresholds) in a background lane, a batch at a time, kept per work in `search.db` with the rules' signature, so a new work, a changed abstract or new rules re-screen only what moved; filters for found in (bibliographies / citing / both), cited by 2+ of yours, names data, open-access PDF; default sort by connections; calibration (recall and precision of the abstract screen measured against the library's full-text verdicts, re-measured as they move; the configured precision only when nothing can be measured); the excluded tallied by reason; near misses (failing exactly one criterion) ranked by connections. The pool upgrade keeps the works and brings their abstracts in as each library paper's network is put back.

## I. Extras
- [ ] **P7** `missing.xlsx`, crawl, saved searches.

## J. Accounts and running it (the template)
- [x] **P1** Login links, users, roles, API keys, sessions, two-factor, activity log, jobs, settings, backups, maintenance, MCP.
- [x] Every screen is full width beside the sidebar (no 60rem cap, unlike the template). Library, Missing and Status are spreadsheet-style tables (`static/js/data_table.js`): click a header to sort (again to flip; Missing keeps tie-breakers), a Columns menu to show, hide and reorder columns, drag a header edge to resize, all remembered per browser; one Filter button whose menu holds every filter. Lists has the same toolbar (search, Filter, Columns, Order, Options) over its board.

## Left behind on purpose
- `snapshot`, `reindex`, `process`, `reprocess`: nothing to run any more.
- Mendeley: Zotero only.
- The TUI and `--exists` minimal mode.
- Anonymous read-only viewing: everything needs sign-in, and the userscripts use an API key.
- The hidden hold-a-key gestures, the "skin" switch, and the `file://` figure reports.
- The hard-coded WSU proxy: it is `library.proxy_url` in config.yaml now.
