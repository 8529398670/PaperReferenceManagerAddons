# PRMA Forwarder (Zotero plugin)

This plugin sends each new paper in desktop Zotero to Paper Reference Manager. Papers can come from the Zotero Connector in the browser, an import, Add Item by Identifier, or anything else. PRMA stores the paper in a ZoteroWebDAV library, and it is searchable in PRMA seconds later.

It works with Zotero 7 through 10.

## Install

1. Build it: `scripts/build_zotero_plugin.sh` writes `dist/prma-zotero.xpi`.
2. Install it in Zotero: **Tools → Plugins**, gear menu, **Install Plugin From File…**, then pick the `.xpi`.
3. Make an API key in PRMA: **Account → API keys**. A user key is enough when you have your own library (see below).
4. In Zotero, open **Tools → PRMA Forwarder Settings…**. Set the address (default `http://127.0.0.1:25620`) and paste the key.
5. Press **Test connection**. It says which library your papers will go to.

## Changing the address or key later

Open **Tools → PRMA Forwarder Settings…** at any time. It opens Zotero's settings at the **PRMA Forwarder** pane (also listed at the bottom of the left side of **Zotero → Settings…**). Edit the address or paste a new key; changes save as you type. Press **Test connection** to check them.

## What it does

- **New papers.** A new top-level item in **My Library** waits until it has had no new attachments or notes for 15 seconds and its PDF has finished downloading. After 3 minutes it is sent with whatever it has. Group libraries are not sent.
- **What is sent.** Zotero's JSON for the paper, its attachments and notes, and the collections it is filed in (with their parents) go to `POST /api/ingest/items`. Then each attachment's file goes to `POST /api/ingest/file`, in 4 MiB pieces.
- **Keys and files.** Zotero keys are kept, so the paper has the same key in Zotero, in ZoteroWebDAV and in PRMA. Files linked outside Zotero's storage folder, such as those ZotFile moved, are uploaded too, and the library keeps its own copy.
- **The desktop copy.** The paper stays in Zotero and gets the tag `prma:sent`, so it is never sent twice on its own.
- **Sending by hand.** Right-click one or more papers → **Send to PRMA** sends them, even if they were sent before. Sending the same paper again changes nothing in the library.
- **Failures.** When a send fails (PRMA is down, or the key is wrong), a short note appears in the corner. The paper is tried again every 5 minutes and when Zotero starts. The settings pane shows how many are waiting.
- **Turning it off.** Untick **Send new papers automatically** to stop the automatic sends. The menu still works.

## Which library it goes to

PRMA decides this, not the plugin:

- If you connected your own ZoteroWebDAV server on PRMA's **Account** screen, papers go there.
- Otherwise they go to the server's library. That needs `library.source: remote` in PRMA's `config.yaml`, and an **admin** key. A user key is refused.
- If the server's library is a local Zotero folder, nothing is stored, because PRMA only reads that folder.

The API key is kept in Zotero's preferences on this computer and is never written to Zotero's debug log.
