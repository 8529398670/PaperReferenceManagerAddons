/* PRMA Forwarder: a bootstrapped Zotero 7+ plugin. The logic is in
 * content/prma.js, which puts Zotero.PRMA in place; this file only starts and
 * stops it and adds the item menu to each main window. */

var PRMA;

function install() {}

async function startup({ id, version, rootURI }) {
  await Zotero.initializationPromise;
  Services.scriptloader.loadSubScript(rootURI + "content/prma.js");
  PRMA = Zotero.PRMA;
  PRMA.init({ id, version, rootURI });
  await PRMA.startup();
  for (const win of Zotero.getMainWindows()) {
    if (win.ZoteroPane) PRMA.addToWindow(win);
  }
}

function onMainWindowLoad({ window }) {
  PRMA?.addToWindow(window);
}

function onMainWindowUnload({ window }) {
  PRMA?.removeFromWindow(window);
}

function shutdown() {
  if (!PRMA) return;
  for (const win of Zotero.getMainWindows()) PRMA.removeFromWindow(win);
  PRMA.shutdown();
  PRMA = undefined;
  delete Zotero.PRMA;
}

function uninstall() {}
