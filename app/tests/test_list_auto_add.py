"""A list's auto_add option: papers newly saved to Zotero join it on their own,
at its top or bottom, after every library sync (BoardService.auto_add)."""
from __future__ import annotations

from app.boards import store as boards
from app.tests.test_lists_routes import MINDALIGN, WOOLRICH, LibraryCase

EARLY = "2026-01-15 00:00:00"  # after Woolrich, before MindAlign and the no-DOI paper


class AutoAddTest(LibraryCase):
    def setUp(self) -> None:
        super().setUp()
        self.service = self.app.state.boards
        boards.create_board(self.store, "Auto", "test")

    def ops(self, batch: list, status: int = 200, slug: str = "auto") -> dict:
        code, body = self.call("POST", f"/api/lists/{slug}/ops", key=self.user_key, body={"ops": batch})
        self.assertEqual(code, status, body)
        return body

    def options(self, slug: str = "auto") -> dict:
        return boards.get_board(self.store, slug)["doc"]["options"]

    def order(self, slug: str = "auto") -> list[str]:
        return [row["key"] for row in boards.get_board(self.store, slug)["doc"]["items"]]

    def switch_on(self, where: str, since: str = EARLY, slug: str = "auto") -> None:
        """auto_add on, with its mark put back to `since` (as if switched on then)."""
        self.ops([{"op": "options", "auto_add": where}], slug=slug)
        boards.apply_ops(self.store, slug, [{"op": "options", "auto_add": where}], self.service.ctx(), "test", set_options={"auto_add_since": since})

    def test_option_is_checked_and_starts_from_now(self) -> None:
        self.assertEqual(self.options()["auto_add"], "off")
        self.ops([{"op": "options", "auto_add": "sideways"}], status=400)
        self.ops([{"op": "options", "auto_add": "top"}])
        options = self.options()
        self.assertEqual(options["auto_add"], "top")
        self.assertGreater(options["auto_add_since"], "2026-03-01 10:00:00")
        # Nothing already in the library is taken.
        self.assertEqual(self.service.auto_add(), [])
        self.assertEqual(self.order(), [])
        # Switching ends keeps the mark; junk in a stored doc is cleaned away.
        mark = options["auto_add_since"]
        self.ops([{"op": "options", "auto_add": "bottom"}])
        self.assertEqual(self.options()["auto_add_since"], mark)
        boards.apply_ops(self.store, "auto", [{"op": "options", "sync": "off"}], self.service.ctx(), "test", set_options={"auto_add": "maybe"})
        self.assertEqual(self.options()["auto_add"], "off")

    def test_top_puts_the_newest_first_and_the_mark_moves_on(self) -> None:
        self.switch_on("top")
        added = self.service.auto_add()
        self.assertEqual(added, [{"slug": "auto", "added": 2}])
        order = self.order()
        self.assertEqual(len(order), 2)
        self.assertEqual(order[1], MINDALIGN)  # older of the two, so below the newest
        self.assertNotIn(WOOLRICH, order)
        self.assertEqual(self.options()["auto_add_since"], "2026-03-01 10:00:00")
        self.assertEqual(boards.get_board(self.store, "auto")["updated_by"], "Zotero auto-add")
        # Nothing new: nothing changes.
        rev = boards.get_board(self.store, "auto")["rev"]
        self.assertEqual(self.service.auto_add(), [])
        self.assertEqual(boards.get_board(self.store, "auto")["rev"], rev)
        # A paper removed from the list is not brought back.
        self.ops([{"op": "remove", "rows": [MINDALIGN]}])
        self.service.auto_add()
        self.assertNotIn(MINDALIGN, self.order())

    def test_bottom_after_a_new_zotero_paper(self) -> None:
        self.ops([{"op": "add", "paper": WOOLRICH}])
        self.switch_on("bottom", since="2026-03-01 10:00:00")
        self.assertEqual(self.service.auto_add(), [])
        self.zotero.add("A brand new paper on auto-adding", added="2026-04-01 09:00:00")
        self.app.state.library.catalogue.sync(force=True)
        self.service.auto_add()
        order = self.order()
        self.assertEqual(order[0], WOOLRICH)
        self.assertEqual(len(order), 2)
        self.assertEqual(self.options()["auto_add_since"], "2026-04-01 09:00:00")

    def test_a_paper_already_on_the_list_is_skipped(self) -> None:
        self.ops([{"op": "add", "paper": MINDALIGN}])
        self.switch_on("bottom")
        self.assertEqual(self.service.auto_add(), [{"slug": "auto", "added": 1}])
        self.assertEqual(self.order()[0], MINDALIGN)
        self.assertEqual(len(self.order()), 2)

    def test_locked_waits_and_off_is_left_alone(self) -> None:
        boards.create_board(self.store, "Other", "test")
        self.switch_on("top")
        boards.set_locked(self.store, "auto", True, "test")
        self.assertEqual(self.service.auto_add(), [])
        self.assertEqual(self.options()["auto_add_since"], EARLY)
        boards.set_locked(self.store, "auto", False, "test")
        self.assertEqual(self.service.auto_add(), [{"slug": "auto", "added": 2}])
        self.assertEqual(self.order("other"), [])

    def test_a_users_own_library_adds_its_new_papers(self) -> None:
        """The Zotero plugin sends to the sender's own library: its sync adds
        that library's new papers, which the server's library does not have."""
        from app.library.catalogue import Catalogue
        from app.library.zotero import Library
        from app.search.index import Index
        from app.tests.zotero_fixture import sample

        own_zotero = sample(self.root / "OwnZotero")
        own_zotero.add("A paper only in my own library", added="2026-04-02 09:00:00")
        index = Index(self.root / "own" / "search.db")
        self.addCleanup(index.close)
        own = Catalogue(Library(self.root / "OwnZotero", self.root / "own"), index)
        own.sync()
        new_key = next(p.key for p in own.all() if p.record["title"].startswith("A paper only in my own"))
        self.assertIsNone(self.app.state.library.catalogue.get(new_key))
        self.switch_on("bottom", since="2026-03-01 10:00:00")
        self.assertEqual(self.service.auto_add(), [])
        self.assertEqual(self.service.auto_add(own), [{"slug": "auto", "added": 1}])
        self.assertEqual(self.order(), [new_key])
        self.assertEqual(self.options()["auto_add_since"], "2026-04-02 09:00:00")
