#!/bin/sh
# Build + syntax check of the bundled game module
cd "$(dirname "$0")" && python3 build.py && python3 - <<'PY' && node --check /tmp/silk_check.mjs && echo SYNTAX_OK
import re
s=open('silkstrike.html',encoding='utf-8').read()
m=re.findall(r'<script type="module">(.*?)</script>',s,re.S)
open('/tmp/silk_check.mjs','w').write(max(m,key=len))
PY
