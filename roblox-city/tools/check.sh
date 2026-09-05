#!/usr/bin/env bash
# Syntaxpruefung aller Luau-Dateien, danach der Testlauf.
#
# Braucht die Luau-CLI: https://github.com/luau-lang/luau/releases
# Entweder in PATH oder ueber LUAU_COMPILE / LUAU.
set -uo pipefail

COMPILE="${LUAU_COMPILE:-luau-compile}"
RUNTIME="${LUAU:-luau}"

if ! command -v "$COMPILE" >/dev/null 2>&1 && [ ! -x "$COMPILE" ]; then
	echo "luau-compile nicht gefunden. Setze LUAU_COMPILE oder lege es in PATH." >&2
	exit 127
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failed=0
count=0

while IFS= read -r file; do
	count=$((count + 1))
	if ! output="$("$COMPILE" --null "$file" 2>&1)"; then
		echo "FEHLER  ${file#"$root"/}"
		echo "$output" | sed 's/^/        /'
		failed=$((failed + 1))
	fi
done < <(find "$root/src" -name '*.luau' | sort)

if [ "$failed" -gt 0 ]; then
	echo "---"
	echo "$failed von $count Dateien fehlerhaft."
	exit 1
fi

echo "$count Dateien, keine Syntaxfehler."

if command -v "$RUNTIME" >/dev/null 2>&1 || [ -x "$RUNTIME" ]; then
	echo "---"
	( cd "$root" && "$RUNTIME" tools/spec.luau ) || exit 1
else
	echo "Hinweis: luau nicht gefunden, Testlauf uebersprungen." >&2
fi
