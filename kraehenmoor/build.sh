#!/usr/bin/env bash
# Baut aus dem Artifact-Fragment eine eigenständige HTML-Datei zum lokalen Spielen.
# Die 3D-Bibliothek wird eingebettet, damit spielen.html auch ohne Internet läuft.
set -e
cd "$(dirname "$0")"
python3 - << 'PY'
import re
src = open('kraehenmoor.html', encoding='utf-8').read()
head = src[src.index('<title>'):src.index('</style>') + len('</style>')]
body = src[src.index('<div id="stage">'):]
three = open('vendor/three.r128.min.js', encoding='utf-8').read()
tag = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
assert tag in head, 'three.js-Einbindung nicht gefunden'
head = head.replace(tag, '<script>' + three.replace('</script', '<\\/script') + '</script>')
out = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
       '<style>html,body{margin:0;padding:0;height:100%;background:#05070a;overflow:hidden}</style>\n'
       + head + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n')
open('spielen.html', 'w', encoding='utf-8').write(out)
print('spielen.html gebaut (%d KB, 3D-Bibliothek eingebettet)' % (len(out.encode()) // 1024))
PY
