/* The PRMA Forwarder settings pane. The fields save themselves (their preference=
 * attributes); this only runs Test connection and shows what is waiting. */
Zotero.PRMAPrefs = {
  init() {
    const waiting = Zotero.PRMA ? Zotero.PRMA.failedKeys().length : 0;
    const label = document.getElementById("prma-waiting");
    if (label) label.value = waiting ? `${waiting} paper(s) failed to send and will be tried again.` : "";
  },

  async test() {
    const status = document.getElementById("prma-status");
    status.value = "Checking…";
    status.value = Zotero.PRMA ? await Zotero.PRMA.testConnection() : "The plugin is not running.";
  },
};
Zotero.PRMAPrefs.init();
