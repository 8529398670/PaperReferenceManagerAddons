"""app/library/mend.py: pairing a remote library's made-up keys with the
local Zotero's, and sending the moves."""
from __future__ import annotations

import unittest
from typing import Any

from app.library import mend
from app.library.mend import Record


def local_library() -> dict[str, Record]:
    records = [
        Record("REALTOP1", "journalArticle", title="No DOI: a paper", date="2020", added="2020-01-02T03:04:05Z", modified="2021-01-01T00:00:00Z"),
        Record("REALPDF1", "attachment", parent="REALTOP1", filename="Café.pdf", added="2020-01-02T03:04:06Z"),
        Record("REALNOT1", "note", parent="REALTOP1", note="<p>Read again</p>", added="2020-01-03T00:00:00Z"),
        Record("REALDOI1", "journalArticle", title="Has a DOI", doi="10.1000/ABC", added="2019-05-05T05:05:05Z"),
        # Two copies of one paper, told apart by their files.
        Record("REALDUP1", "book", title="Twice", date="1999", added="2018-01-01T00:00:00Z"),
        Record("REALDPF1", "attachment", parent="REALDUP1", filename="first.pdf"),
        Record("REALDUP2", "book", title="Twice", date="1999", added="2018-02-02T00:00:00Z"),
        Record("REALDPF2", "attachment", parent="REALDUP2", filename="second.pdf"),
        Record("LOCALONL", "book", title="Only here", added="2026-01-01T00:00:00Z"),
    ]
    return {r.key: r for r in records}


def server_library() -> dict[str, Record]:
    records = [
        Record("MADETOP1", "journalArticle", title="No DOI - a Paper", date="2020-03"),
        # Decomposed é, as a macOS zip can write it.
        Record("MADEPDF1", "attachment", parent="MADETOP1", filename="Café.pdf"),
        Record("MADENOT1", "note", parent="MADETOP1", note="<p>Read again</p>"),
        Record("MADEDOI1", "journalArticle", title="Has a DOI (other title)", doi="https://doi.org/10.1000/abc"),
        Record("MADEDUP1", "book", title="Twice", date="1999"),
        Record("MADEDPF2", "attachment", parent="MADEDUP1", filename="second.pdf"),
        Record("MADEDUP2", "book", title="Twice", date="1999"),
        Record("MADEDPF1", "attachment", parent="MADEDUP2", filename="first.pdf"),
        Record("SERVERON", "book", title="Only there"),
    ]
    return {r.key: r for r in records}


class PlanTest(unittest.TestCase):
    def test_pairs_every_record_it_can(self) -> None:
        mended = mend.plan(local_library(), server_library())
        to = {move["from"]: move.get("to") for move in mended.moves}
        self.assertEqual(to["MADETOP1"], "REALTOP1")
        self.assertEqual(to["MADEPDF1"], "REALPDF1")
        self.assertEqual(to["MADENOT1"], "REALNOT1")
        self.assertEqual(to["MADEDOI1"], "REALDOI1")
        self.assertEqual(to["MADEDUP1"], "REALDUP2")  # holds second.pdf
        self.assertEqual(to["MADEDPF2"], "REALDPF2")
        self.assertEqual(to["MADEDUP2"], "REALDUP1")
        self.assertEqual(mended.unpaired_local, ["LOCALONL"])
        self.assertEqual(mended.unpaired_server, ["SERVERON"])
        self.assertEqual(mended.ambiguous, [])
        top = next(move for move in mended.moves if move["from"] == "MADETOP1")
        self.assertEqual(top["set"], {"dateAdded": "2020-01-02T03:04:05Z", "dateModified": "2021-01-01T00:00:00Z"})
        # A paper and its children travel together.
        tree = next(t for t in mended.trees if t[0]["from"] == "MADETOP1")
        self.assertEqual({m["from"] for m in tree}, {"MADETOP1", "MADEPDF1", "MADENOT1"})

    def test_copies_that_cannot_be_told_apart_are_left(self) -> None:
        local, server = local_library(), server_library()
        local["REALDPF2"].filename = "first.pdf"  # but the server's differ
        mended = mend.plan(local, server)
        moved = {move["from"] for move in mended.moves}
        self.assertNotIn("MADEDUP1", moved)
        self.assertNotIn("MADEDUP2", moved)
        self.assertEqual(sorted(mended.ambiguous), ["REALDUP1", "REALDUP2"])

    def test_copies_alike_in_everything_are_paired_in_order(self) -> None:
        local, server = local_library(), server_library()
        local["REALDPF2"].filename = server["MADEDPF2"].filename = "first.pdf"
        mended = mend.plan(local, server)
        to = {m["from"]: m.get("to") for m in mended.moves}
        self.assertEqual({to["MADEDUP1"], to["MADEDUP2"]}, {"REALDUP1", "REALDUP2"})
        self.assertEqual(mended.twins, 1)  # the first choice; the second is what is left
        self.assertEqual(mended.ambiguous, [])

    def test_already_mended_is_nothing_to_do(self) -> None:
        local = local_library()
        server = {key: Record(**{**vars(record)}) for key, record in local.items()}
        mended = mend.plan(local, server)
        self.assertEqual(mended.moves, [])
        self.assertEqual(mended.paired, len(local))


class TwinsByFileTest(unittest.TestCase):
    def test_copies_with_one_file_name_are_told_apart_by_md5(self) -> None:
        local, server = local_library(), server_library()
        for record, md5 in ((local["REALDPF1"], "a" * 32), (local["REALDPF2"], "b" * 32),
                            (server["MADEDPF1"], "a" * 32), (server["MADEDPF2"], "b" * 32)):
            record.filename, record.md5 = "same.pdf", md5
        to = {m["from"]: m.get("to") for m in mend.plan(local, server).moves}
        self.assertEqual(to["MADEDUP2"], "REALDUP1")
        self.assertEqual(to["MADEDPF1"], "REALDPF1")

    def test_a_note_matches_whatever_html_wraps_it(self) -> None:
        local, server = local_library(), server_library()
        local["REALNOT1"].note = '<div class="zotero-note znv1"><p>Read&nbsp;again</p></div>'
        server["MADENOT1"].note = "Read again"
        to = {m["from"]: m.get("to") for m in mend.plan(local, server).moves}
        self.assertEqual(to["MADENOT1"], "REALNOT1")


class MendedTwiceTest(unittest.TestCase):
    def test_a_second_plan_moves_nothing_even_for_copies(self) -> None:
        local, server = local_library(), server_library()
        local["REALDPF2"].filename = server["MADEDPF2"].filename = "first.pdf"
        mended = mend.plan(local, server)
        # The server after the moves: every record under the key it went to.
        after = {}
        moves = {m["from"]: m for m in mended.moves}
        for key, record in server.items():
            move = moves.get(key, {})
            new = Record(**vars(record))
            new.key = move.get("to", key)
            new.parent = moves.get(record.parent, {}).get("to", record.parent)
            new.added, new.modified = move.get("set", {}).get("dateAdded", record.added), move.get("set", {}).get("dateModified", record.modified)
            after[new.key] = new
        again = mend.plan(local, after)
        self.assertEqual(again.moves, [])
        self.assertEqual(again.unpaired_server, [k for k in after if k not in local])


class FakeRemote:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post_json(self, path: str, body: dict[str, Any], timeout: int = 0) -> dict[str, Any]:
        self.calls.append(body)
        return {"results": [{"from": m["from"], "to": m.get("to", m["from"]), "status": "moved", "files": True} for m in body["items"]]}


class ApplyTest(unittest.TestCase):
    def test_batches_keep_trees_whole(self) -> None:
        mended = mend.Plan(trees=[[{"from": f"T{n:03d}", "to": f"R{n:03d}"}] * 3 for n in range(700)])
        remote = FakeRemote()
        sent = mend.apply(remote, mended)  # type: ignore[arg-type]
        self.assertEqual(sent["statuses"], {"moved": 2100})
        self.assertTrue(all(len(call["items"]) <= mend.BATCH and len(call["items"]) % 3 == 0 for call in remote.calls))
        self.assertFalse(remote.calls[0]["dry_run"])


if __name__ == "__main__":
    unittest.main()
