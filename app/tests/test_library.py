"""The library: reading Zotero, keeping up with it one paper at a time, and
searching it. Against a small fake Zotero (zotero_fixture.py)."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from app.library.catalogue import Catalogue
from app.library.zotero import Library, normalize_doi, synthetic_key
from app.search import query as q
from app.search.index import Index
from app.tests.zotero_fixture import sample


class QueryTest(unittest.TestCase):
    def test_fold(self) -> None:
        self.assertEqual(q.fold("MindAlign: Decoding  Inner–Speech"), "mindalign decoding inner speech")
        self.assertEqual(q.fold("Ørsted naïve café"), "orsted naive cafe")
        self.assertEqual(q.fold("10.1002/(SICI)1099"), "10 1002 sici 1099")

    def test_parse(self) -> None:
        clauses = q.parse('decoding "inner speech" -EEG OR imagined NOT overt')
        self.assertEqual([(c.pos, c.neg) for c in clauses], [(["decoding", "inner speech"], ["eeg"]), (["imagined"], ["overt"])])
        self.assertEqual(q.parse('"fight or flight"')[0].pos, ["fight or flight"])
        self.assertEqual(q.parse("   "), [])

    def test_doi_and_keys(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1038/nn.4244/figures/2"), "10.1038/nn.4244")
        self.assertIsNone(normalize_doi("no doi here"))
        self.assertEqual(synthetic_key("AB CD"), "nodoi-zotero-AB-CD")


class CatalogueTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.zotero = sample(root / "Zotero")
        self.index = Index(root / "cache" / "search.db")
        self.addCleanup(self.index.close)
        self.catalogue = Catalogue(Library(root / "Zotero", root / "cache"), self.index)
        self.events: list[str] = []
        self.catalogue.on_event = lambda name, data: self.events.append(name)

    def test_first_sync_reads_everything_then_nothing(self) -> None:
        result = self.catalogue.sync()
        self.assertEqual((result.added, result.texts), (3, 3))
        self.assertEqual(self.catalogue.status.with_text, 2)
        self.assertIsNone(self.catalogue.sync())
        again = self.catalogue.sync(force=True)
        self.assertFalse(again.any())

    def test_one_change_touches_one_paper(self) -> None:
        self.catalogue.sync()
        key = self.zotero.add("A new paper on decoding", doi="10.1000/new", text="body words xylophone", added="2026-04-01 00:00:00")
        self.bump()
        result = self.catalogue.sync()
        self.assertEqual((result.added, result.changed, result.removed, result.texts), (1, 0, 0, 1))
        self.assertEqual([p.key for p in self.catalogue.search("xylophone").rows], ["10.1000/new"])

        self.zotero.set_title(key, "A renamed paper", "2026-04-02 00:00:00")
        self.bump()
        result = self.catalogue.sync()
        self.assertEqual((result.added, result.changed, result.texts), (0, 1, 0))
        self.assertEqual(self.catalogue.get("10.1000/new").record["title"], "A renamed paper")

        self.zotero.delete(key)
        self.bump()
        self.assertEqual(self.catalogue.sync().removed, 1)
        self.assertEqual(self.catalogue.search("xylophone").rows, [])

    def test_text_zotero_writes_later_lands_by_itself(self) -> None:
        self.catalogue.sync()
        path = self.zotero.fulltext_path("ITEM0002")
        path.write_text("entirely new words: quokka")
        stamp = time.time() + 5
        os.utime(path, (stamp, stamp))
        result = self.catalogue.sync(force=True)
        self.assertEqual(result.texts, 1)
        self.assertEqual(len(self.catalogue.search("quokka").rows), 1)

    def test_restart_needs_no_reindex(self) -> None:
        self.catalogue.sync()
        fresh = Catalogue(Library(self.zotero.folder, self.index.path.parent), self.index)
        fresh.load()
        self.assertEqual(len(fresh.all()), 3)
        result = fresh.sync()
        self.assertFalse(result.any())

    def test_search(self) -> None:
        self.catalogue.sync()
        titles = lambda text, mode="text": [p.record["title"][:20] for p in self.catalogue.search(text, mode).rows]
        # Full text, abstract, phrase, exclusion, OR.
        self.assertEqual(titles("prewhitening"), ["Temporal Autocorrela"])
        self.assertEqual(titles("embeddings"), ["MindAlign: Decoding "])
        self.assertEqual(titles('"inner speech" -EEG'), ["Temporal Autocorrela"])
        self.assertEqual(len(titles("prewhitening OR embeddings")), 2)
        # Accents folded on both sides.
        self.assertEqual(titles("orsted cafe"), ["A paper with no DOI "])
        # The title outranks a mention in the body.
        self.assertEqual(titles("decoding inner speech")[0], "MindAlign: Decoding ")
        # A typo in title mode; a pasted DOI.
        self.assertEqual(titles("temporal autocorelation fmri", "title")[0], "Temporal Autocorrela")
        self.assertEqual(titles("10.48550/arXiv.2606.20696", "title")[0], "MindAlign: Decoding ")
        # Nothing matches: the closest titles, said to be so.
        result = self.catalogue.search("mindalgn decodin")
        self.assertTrue(result.fuzzy)

    def test_exists(self) -> None:
        self.catalogue.sync()
        self.assertTrue(self.catalogue.exists("https://doi.org/10.1006/NIMG.2001.0931", ""))
        self.assertFalse(self.catalogue.exists("10.9999/none", "Temporal Autocorrelation in Univariate Linear Modeling of FMRI Data"))
        self.assertTrue(self.catalogue.exists("", "temporal autocorrelation in univariate linear modeling of fmri data."))
        self.assertFalse(self.catalogue.exists("", "Something else entirely"))

    def bump(self) -> None:
        """A commit Zotero made: the file's mtime moves on."""
        stamp = time.time() + 1
        os.utime(self.zotero.path, (stamp, stamp))
        self.catalogue._text_checked = 0


if __name__ == "__main__":
    unittest.main()
