#!/usr/bin/env python3
"""Fügt alle Swift-Dateien von Silkstrike.swiftpm zu EINER Datei zusammen
(Silkstrike_KOMPLETT.swift) und prüft auf doppelte Namen auf oberster Ebene."""
import os, re, sys, collections

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Silkstrike.swiftpm")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Silkstrike_KOMPLETT.swift")
ORDER = ["Core", "Graphics", "Character", "Audio", "Data", "World", "Kombat", "Cutscene", "UI", "App"]

DECL = re.compile(r'^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|internal|private|fileprivate|final|static|indirect|open)\s+)*'
                  r'(class|struct|enum|protocol|typealias|func|let|var|extension)\s+([A-Za-z_][A-Za-z0-9_]*)')

def strip_code(line, state):
    """Entfernt Strings und Kommentare (grob) für die Klammerzählung. state: in_block_comment, in_multiline_string"""
    out = []
    i = 0
    while i < len(line):
        if state["block"]:
            j = line.find("*/", i)
            if j < 0: return "".join(out)
            state["block"] = False; i = j + 2; continue
        if state["mstr"]:
            j = line.find('"""', i)
            if j < 0: return "".join(out)
            state["mstr"] = False; i = j + 3; continue
        if line.startswith("//", i): break
        if line.startswith("/*", i): state["block"] = True; i += 2; continue
        if line.startswith('"""', i): state["mstr"] = True; i += 3; continue
        c = line[i]
        if c == '"':
            j = i + 1
            depth = 0
            while j < len(line):
                if line[j] == "\\" and j + 1 < len(line) and line[j+1] == "(":
                    depth += 1; j += 2; continue
                if depth and line[j] == ")": depth -= 1; j += 1; continue
                if line[j] == "\\": j += 2; continue
                if line[j] == '"' and depth == 0: break
                j += 1
            i = j + 1; out.append('""'); continue
        out.append(c); i += 1
    return "".join(out)

def files_in_order():
    result = []
    for d in ORDER:
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p): continue
        for dirpath, _, names in sorted(os.walk(p)):
            for n in sorted(names):
                if n.endswith(".swift"): result.append(os.path.join(dirpath, n))
    # alles andere (falls neue Ordner)
    for dirpath, _, names in sorted(os.walk(ROOT)):
        for n in sorted(names):
            f = os.path.join(dirpath, n)
            if n.endswith(".swift") and n != "Package.swift" and f not in result:
                result.append(f)
    return result

def main():
    files = files_in_order()
    imports = set()
    bodies = []
    top = collections.defaultdict(list)      # name -> [file:line]
    ext_members = collections.defaultdict(list)
    for f in files:
        rel = os.path.relpath(f, ROOT)
        lines = open(f, encoding="utf-8").read().split("\n")
        state = {"block": False, "mstr": False}
        depth = 0
        ext_stack = []   # (type, depth)
        kept = []
        for ln, line in enumerate(lines, 1):
            s = line.strip()
            if depth == 0 and re.match(r'^(@preconcurrency\s+)?import\s+\w+', s) and not state["block"] and not state["mstr"]:
                imports.add(s); continue
            code = strip_code(line, state) if True else line
            m = DECL.match(code)
            if m and depth == 0:
                kind, name = m.group(1), m.group(2)
                if kind == "extension":
                    ext_stack.append((name, depth + 1))
                else:
                    top[name].append(f"{rel}:{ln}")
            elif m and ext_stack and depth == ext_stack[-1][1] and m.group(1) in ("func", "var", "let", "class", "struct", "enum", "typealias"):
                if m.group(1) != "func":  # funcs dürfen überladen werden; Signaturen prüfen wir nicht
                    ext_members[(ext_stack[-1][0], m.group(2))].append(f"{rel}:{ln}")
                else:
                    ext_members[(ext_stack[-1][0], m.group(2) + "()")].append(f"{rel}:{ln}")
            depth += code.count("{") - code.count("}")
            while ext_stack and depth < ext_stack[-1][1]:
                ext_stack.pop()
            kept.append(line)
        bodies.append(f"\n// =====================================================================\n// MARK: - {rel}\n// =====================================================================\n\n" + "\n".join(kept).strip("\n") + "\n")
    problems = [(n, locs) for n, locs in top.items() if len(locs) > 1]
    ext_problems = [(k, locs) for k, locs in ext_members.items() if len(set(l.split(':')[0] for l in locs)) > 1]
    header = ("// SILKSTRIKE – Blutturnier\n"
              "// Komplettes Spiel in EINER Datei für Swift Playgrounds / Xcode.\n"
              "// Anleitung: siehe SILKSTRIKE_ANLEITUNG.md\n"
              "// Automatisch erzeugt aus Silkstrike.swiftpm – nicht von Hand bearbeiten.\n\n")
    with open(OUT, "w", encoding="utf-8") as o:
        o.write(header + "\n".join(sorted(imports)) + "\n" + "".join(bodies))
    total = sum(1 for _ in open(OUT, encoding="utf-8"))
    print(f"{len(files)} Dateien -> {os.path.relpath(OUT)} ({total} Zeilen)")
    if problems or ext_problems:
        print("DOPPELTE NAMEN:")
        for n, locs in sorted(problems): print(f"  {n}: {', '.join(locs)}")
        for (t, n), locs in sorted(ext_problems): print(f"  extension {t}.{n}: {', '.join(locs)}")
        sys.exit(1)
    print("Keine doppelten Namen gefunden.")

if __name__ == "__main__":
    main()
