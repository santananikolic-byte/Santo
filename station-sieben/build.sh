#!/usr/bin/env bash
# Baut aus dem Artifact-Fragment eine eigenstaendige HTML-Datei zum lokalen Spielen.
set -e
cd "$(dirname "$0")"
{
  printf '%s\n' '<!doctype html>' '<html lang="de">' '<head>' '<meta charset="utf-8">' \
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' \
    '<style>html,body{margin:0;padding:0;height:100%;background:#05070a;overflow:hidden}img{max-width:100%}</style>'
  sed -n '/<title>/,/<\/style>/p' station-sieben.html
  printf '%s\n' '</head>' '<body>'
  sed -n '/<div id="stage">/,$p' station-sieben.html
  printf '%s\n' '</body>' '</html>'
} > spielen.html
echo "spielen.html gebaut ($(wc -c < spielen.html) Bytes)"
