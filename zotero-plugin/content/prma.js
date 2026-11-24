/* PRMA Forwarder: sends new papers to Paper Reference Manager.
 *
 * A paper added to the user library (by the Zotero Connector, an import, a
 * DOI lookup...) is sent once it has settled: no new attachments or notes for
 * QUIET_MS, and every stored attachment's file on disk (a PDF still
 * downloading has none yet). After MAX_WAIT_MS it is sent with what it has.
 *
 * Sending is POST {url}/api/ingest/items with Zotero's JSON for the paper,
 * its attachments and notes, and the collections it is in (with their
 * parents), then each attachment's file in CHUNK-sized pieces to
 * POST {url}/api/ingest/file. PRMA stores them in a ZoteroWebDAV library under
 * the same keys. The paper then gets the tag prma:sent, so it is never sent
 * twice on its own; right-click → Send to PRMA sends any paper again.
 *
 * A file or note added later to a paper already sent (a PDF found or
 * attached by hand after the Connector saved only the metadata) sends that
 * paper again once the file is on disk, uploading only the new files.
 *
 * A failed send is kept (extensions.prma.retryQueue) and tried again every
 * RETRY_MS and at startup. The API key is never logged. */

(function () {
  const { setTimeout, clearTimeout, setInterval, clearInterval } =
    ChromeUtils.importESModule("resource://gre/modules/Timer.sys.mjs");

  const PREF = "extensions.prma.";
  const SENT_TAG = "prma:sent";
  const QUIET_MS = 15 * 1000;
  const RECHECK_MS = 5 * 1000;
  const MAX_WAIT_MS = 3 * 60 * 1000;
  const RETRY_MS = 5 * 60 * 1000;
  const RECENT_MS = 10 * 60 * 1000; // an attachment for a paper added this recently wakes it
  const CHUNK = 4 * 1024 * 1024; // PRMA's chunk_bytes (GET /api/ingest/target says it too)
  const MENU_ID = "prma-send-menuitem";
  const MENU_SEP_ID = "prma-send-separator";
  const TOOLS_MENU_ID = "prma-settings-menuitem";
  const PANE_ID = "prma-forwarder-prefs";

  const PRMA = {
    id: "",
    version: "",
    rootURI: "",
    observerID: null,
    retryTimer: null,
    pending: new Map(), // parent item id -> { first, timer, later, newKeys }
    sending: new Set(), // parent item keys being sent now
    chunk: CHUNK,

    init({ id, version, rootURI }) {
      this.id = id;
      this.version = version;
      this.rootURI = rootURI;
    },

    // -- prefs -------------------------------------------------------------

    pref(name) {
      return Zotero.Prefs.get(PREF + name, true);
    },

    setPref(name, value) {
      Zotero.Prefs.set(PREF + name, value, true);
    },

    apiKey() {
      return String(this.pref("apiKey") || "").trim();
    },

    baseURL() {
      return String(this.pref("url") || "").trim().replace(/\/+$/, "");
    },

    log(message) {
      Zotero.debug("PRMA: " + message);
    },

    // -- lifecycle ---------------------------------------------------------

    async startup() {
      Zotero.PreferencePanes.register({
        pluginID: this.id,
        src: this.rootURI + "preferences.xhtml",
        scripts: [this.rootURI + "preferences.js"],
        id: PANE_ID,
        label: "PRMA Forwarder",
      });
      this.observerID = Zotero.Notifier.registerObserver(
        { notify: (event, type, ids, extra) => this.notify(event, type, ids, extra) },
        ["item"],
        "prma",
      );
      this.retryTimer = setInterval(() => this.retryFailed(), RETRY_MS);
      setTimeout(() => this.retryFailed(), 20 * 1000);
      this.log("started " + this.version);
    },

    shutdown() {
      if (this.observerID) Zotero.Notifier.unregisterObserver(this.observerID);
      this.observerID = null;
      if (this.retryTimer) clearInterval(this.retryTimer);
      this.retryTimer = null;
      for (const entry of this.pending.values()) clearTimeout(entry.timer);
      this.pending.clear();
    },

    // -- the item menu -----------------------------------------------------

    addToWindow(win) {
      const doc = win.document;
      const menu = doc.getElementById("zotero-itemmenu");
      if (!menu || doc.getElementById(MENU_ID)) return;
      const separator = doc.createXULElement("menuseparator");
      separator.id = MENU_SEP_ID;
      const item = doc.createXULElement("menuitem");
      item.id = MENU_ID;
      item.setAttribute("label", "Send to PRMA");
      item.addEventListener("command", () => this.sendSelected(win));
      menu.appendChild(separator);
      menu.appendChild(item);

      // Tools → PRMA Forwarder Settings… opens the settings pane directly.
      const tools = doc.getElementById("menu_ToolsPopup");
      if (tools && !doc.getElementById(TOOLS_MENU_ID)) {
        const settings = doc.createXULElement("menuitem");
        settings.id = TOOLS_MENU_ID;
        settings.setAttribute("label", "PRMA Forwarder Settings…");
        settings.addEventListener("command", () => this.openSettings());
        tools.appendChild(settings);
      }
    },

    removeFromWindow(win) {
      for (const id of [MENU_ID, MENU_SEP_ID, TOOLS_MENU_ID]) win.document.getElementById(id)?.remove();
    },

    openSettings() {
      Zotero.Utilities.Internal.openPreferences(PANE_ID);
    },

    async sendSelected(win) {
      const parents = new Map();
      for (const item of win.ZoteroPane.getSelectedItems()) {
        const parent = item.isTopLevelItem() ? item : Zotero.Items.get(item.parentItemID);
        if (parent && parent.isRegularItem()) parents.set(parent.id, parent);
      }
      if (!parents.size) {
        this.toast("Pick a paper first: notes and stand-alone files are not sent.", true);
        return;
      }
      let ok = 0;
      const failures = [];
      for (const parent of parents.values()) {
        try {
          await this.send(parent);
          ok += 1;
        } catch (error) {
          failures.push(error.message);
        }
      }
      if (failures.length) {
        this.toast(`Sent ${ok} of ${parents.size} to PRMA. ${failures[0]}`, true);
      } else {
        this.toast(ok === 1 ? "Sent to PRMA." : `Sent ${ok} papers to PRMA.`);
      }
    },

    // -- watching for new papers -------------------------------------------

    notify(event, type, ids) {
      if (event !== "add" || type !== "item" || !this.pref("autoSend")) return;
      for (const id of ids) {
        const item = Zotero.Items.get(id);
        if (!item || item.libraryID !== Zotero.Libraries.userLibraryID) continue;
        if (item.isRegularItem() && item.isTopLevelItem()) {
          this.schedule(item.id);
        } else if (item.parentItemID) {
          // An attachment or note: its paper waits a little longer.
          const parent = Zotero.Items.get(item.parentItemID);
          if (!parent || !parent.isRegularItem() || !parent.isTopLevelItem()) continue;
          if (parent.hasTag(SENT_TAG)) {
            // Added after the paper was sent: send it again with this one.
            this.schedule(parent.id, QUIET_MS, item.key);
            continue;
          }
          const added = Zotero.Date.sqlToDate(parent.dateAdded, true);
          const recent = added && Date.now() - added.getTime() < RECENT_MS;
          if (this.pending.has(parent.id) || recent) this.schedule(parent.id);
        }
      }
    },

    schedule(itemID, delay = QUIET_MS, laterKey = "") {
      const entry = this.pending.get(itemID) || { first: Date.now(), timer: null, later: false, newKeys: new Set() };
      if (laterKey) {
        entry.later = true;
        entry.newKeys.add(laterKey);
      }
      if (entry.timer) clearTimeout(entry.timer);
      entry.timer = setTimeout(() => this.settle(itemID), delay);
      this.pending.set(itemID, entry);
    },

    async settle(itemID) {
      const entry = this.pending.get(itemID);
      const item = Zotero.Items.get(itemID);
      if (!entry || !item || item.deleted) {
        this.pending.delete(itemID);
        return;
      }
      if (item.hasTag(SENT_TAG) && !entry.later) {
        this.pending.delete(itemID);
        return;
      }
      const waiting = await this.filesMissing(item);
      if (waiting && Date.now() - entry.first < MAX_WAIT_MS) {
        entry.timer = setTimeout(() => this.settle(itemID), RECHECK_MS);
        return;
      }
      this.pending.delete(itemID);
      try {
        // A later addition uploads only its own files; the rest are there.
        await this.send(item, entry.later ? entry.newKeys : null);
        this.log(`sent ${item.key}`);
        if (entry.later) this.toast(`Sent the new file or note of “${this.shortTitle(item)}” to PRMA.`);
      } catch (error) {
        this.toast(`Could not send “${this.shortTitle(item)}” to PRMA: ${error.message} It will be tried again.`, true);
      }
    },

    async filesMissing(item) {
      for (const att of Zotero.Items.get(item.getAttachments())) {
        if (this.isStored(att) && !(await att.fileExists())) return true;
      }
      return false;
    },

    isStored(att) {
      const mode = att.attachmentLinkMode;
      return mode === Zotero.Attachments.LINK_MODE_IMPORTED_FILE || mode === Zotero.Attachments.LINK_MODE_IMPORTED_URL;
    },

    hasFile(att) {
      // Stored files, and linked files too (ZotFile moves PDFs out of storage):
      // the library then keeps a copy of their own.
      return this.isStored(att) || att.attachmentLinkMode === Zotero.Attachments.LINK_MODE_LINKED_FILE;
    },

    // -- sending -----------------------------------------------------------

    // onlyFiles: a Set of attachment keys whose files to upload; null uploads every file.
    async send(item, onlyFiles = null) {
      if (!this.baseURL() || !this.apiKey()) {
        throw new Error("Set PRMA's address and an API key under Tools → PRMA Forwarder Settings.");
      }
      if (this.sending.has(item.key)) return;
      this.sending.add(item.key);
      try {
        await this.sendNow(item, onlyFiles);
        this.forgetFailed(item.key);
        if (!item.hasTag(SENT_TAG)) {
          item.addTag(SENT_TAG);
          await item.saveTx({ skipDateModifiedUpdate: true });
        }
      } catch (error) {
        this.rememberFailed(item.key);
        throw error;
      } finally {
        this.sending.delete(item.key);
      }
    },

    async sendNow(item, onlyFiles = null) {
      const children = Zotero.Items.get([...item.getAttachments(), ...item.getNotes()]);
      const parentJSON = item.toJSON();
      // The tag goes with it, so the library says it came this way.
      if (!(parentJSON.tags || []).some((t) => t.tag === SENT_TAG)) {
        parentJSON.tags = [...(parentJSON.tags || []), { tag: SENT_TAG }];
      }
      const records = [item, ...children].map((x, i) => {
        const data = i === 0 ? parentJSON : x.toJSON();
        data.key = x.key;
        return { key: x.key, data };
      });
      const collections = this.collectionsOf(item).map((c) => ({ key: c.key, data: Object.assign(c.toJSON(), { key: c.key }) }));
      const reply = await this.request("POST", "/api/ingest/items", JSON.stringify({ items: records, collections }), "application/json");
      const failed = (reply.results || []).filter((r) => !r.ok);
      if (failed.length) throw new Error(`PRMA did not store ${failed[0].key}: ${failed[0].error}`);
      for (const att of children) {
        if (!att.isAttachment() || !this.hasFile(att)) continue;
        if (onlyFiles && !onlyFiles.has(att.key)) continue;
        const path = await att.getFilePathAsync();
        if (!path) continue;
        await this.upload(att, path);
      }
    },

    collectionsOf(item) {
      const found = new Map();
      for (const id of item.getCollections()) {
        let collection = Zotero.Collections.get(id);
        while (collection && !found.has(collection.key)) {
          found.set(collection.key, collection);
          collection = collection.parentID ? Zotero.Collections.get(collection.parentID) : null;
        }
      }
      // Parents first; PRMA sorts them too.
      return [...found.values()].reverse();
    },

    async upload(att, path) {
      const info = await IOUtils.stat(path);
      const size = info.size;
      if (!size) return;
      const name = att.attachmentFilename || PathUtils.filename(path);
      const mtime = Math.round(info.lastModified || Date.now());
      for (let offset = 0; offset < size; offset += this.chunk) {
        const bytes = await IOUtils.read(path, { offset, maxBytes: Math.min(this.chunk, size - offset) });
        const query = new URLSearchParams({ key: att.key, filename: name, size: String(size), offset: String(offset), mtime: String(mtime) });
        const reply = await this.request("POST", "/api/ingest/file?" + query, bytes, "application/octet-stream");
        if (offset + this.chunk >= size && !reply.done) throw new Error(`PRMA did not finish the file ${name}.`);
      }
    },

    async request(method, path, body, contentType) {
      const headers = { Authorization: "Bearer " + this.apiKey(), Accept: "application/json" };
      if (contentType) headers["Content-Type"] = contentType;
      let response;
      try {
        response = await this.fetch(this.baseURL() + path, { method, headers, body });
      } catch (error) {
        throw new Error("PRMA could not be reached at " + this.baseURL() + ".");
      }
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        data = {};
      }
      if (!response.ok) {
        const why = data.error || `HTTP ${response.status}`;
        if (response.status === 401) throw new Error("PRMA refused the API key: check it under Tools → PRMA Forwarder Settings.");
        throw new Error(why.endsWith(".") ? why : why + ".");
      }
      return data;
    },

    fetch(url, options) {
      if (typeof fetch === "function") return fetch(url, options);
      const win = Zotero.getMainWindow();
      return win.fetch(url, options);
    },

    async testConnection() {
      if (!this.baseURL()) return "Set PRMA's address first.";
      if (!this.apiKey()) return "Paste an API key from PRMA first.";
      try {
        const target = await this.request("GET", "/api/ingest/target");
        if (target.chunk_bytes) this.chunk = target.chunk_bytes;
        if (!target.writable) return "Connected, but papers cannot be stored: " + target.reason;
        return target.kind === "own" ? "Connected: papers go to your own library." : "Connected: papers go to the server's library.";
      } catch (error) {
        return error.message;
      }
    },

    // -- retrying ----------------------------------------------------------

    failedKeys() {
      try {
        const keys = JSON.parse(this.pref("retryQueue") || "[]");
        return Array.isArray(keys) ? keys : [];
      } catch (error) {
        return [];
      }
    },

    rememberFailed(key) {
      const keys = this.failedKeys();
      if (!keys.includes(key)) this.setPref("retryQueue", JSON.stringify([...keys, key].slice(-500)));
    },

    forgetFailed(key) {
      const keys = this.failedKeys();
      if (keys.includes(key)) this.setPref("retryQueue", JSON.stringify(keys.filter((k) => k !== key)));
    },

    async retryFailed() {
      const keys = this.failedKeys();
      if (!keys.length || !this.baseURL() || !this.apiKey()) return;
      let sent = 0;
      for (const key of keys) {
        const item = Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID, key);
        if (!item || item.deleted || !item.isRegularItem()) {
          this.forgetFailed(key);
          continue;
        }
        try {
          await this.send(item);
          sent += 1;
        } catch (error) {
          this.log(`retry of ${key} failed: ${error.message}`);
          break; // PRMA is still away: try the rest next time
        }
      }
      if (sent) this.toast(sent === 1 ? "Sent 1 waiting paper to PRMA." : `Sent ${sent} waiting papers to PRMA.`);
    },

    // -- words -------------------------------------------------------------

    shortTitle(item) {
      const title = item.getField("title") || item.key;
      return title.length > 60 ? title.slice(0, 57) + "…" : title;
    },

    toast(text, isError = false) {
      try {
        const progress = new Zotero.ProgressWindow({ closeOnClick: true });
        progress.changeHeadline(isError ? "PRMA: not sent" : "PRMA");
        progress.addDescription(text);
        progress.show();
        progress.startCloseTimer(isError ? 8000 : 3000);
      } catch (error) {
        this.log(text);
      }
    },
  };

  Zotero.PRMA = PRMA;
})();
