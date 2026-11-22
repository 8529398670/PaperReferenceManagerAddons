#!/usr/bin/env bash
# Build the Zotero plugin (zotero-plugin/) into dist/prma-zotero.xpi.
#
#   scripts/build_zotero_plugin.sh
#
# Install it in Zotero: Tools → Plugins → gear menu → Install Plugin From
# File…, then set PRMA's address and an API key under Tools → PRMA Forwarder Settings. See
# zotero-plugin/README.md.
set -euo pipefail
cd "$( dirname "${BASH_SOURCE[0]}" )/.."
out="dist/prma-zotero.xpi"
mkdir -p dist
rm -f "$out"
version=$( python3 -c 'import json; print(json.load(open("zotero-plugin/manifest.json"))["version"])' )
( cd zotero-plugin && zip -q -r -X "../$out" manifest.json bootstrap.js prefs.js preferences.xhtml preferences.js content )
echo "wrote $out (version $version)"
