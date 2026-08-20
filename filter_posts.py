"""Filtre les publications Facebook : suppression et remplacement d'éléments sensibles.

Règles (issues de filter.txt) :
  1. Supprimer les posts « a écrit sur le profil de <Nom> »
  2. Remplacer toutes les adresses IP (IPv4 / IPv6) par xxxxx
  3. Remplacer @[1318849741:2048:Salim Benfarhat] par xxxxx
  4. Remplacer « Salim Benfarhat » par xxxxx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_JSON = Path("data/your_posts__check_ins__photos_and_videos_1.json")

# ── 1. Suppression de posts ──────────────────────────────────────────────────

_DELETE_PATTERNS = [
    re.compile(r"a \u00c3\u00a9crit sur le profil de\b", re.IGNORECASE),
    re.compile(r"a écrit sur le profil de\b", re.IGNORECASE),
]


def _should_delete(entry: dict) -> bool:
    title = entry.get("title", "")
    return any(p.search(title) for p in _DELETE_PATTERNS)


# ── 2. Remplacements dans les chaînes ────────────────────────────────────────

_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_IPV6_RE = re.compile(r"\b[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}\b")

_STRING_REPLACEMENTS: list[tuple[str, str]] = [
    ("@[1318849741:2048:Salim Benfarhat]", "xxxxx"),
    ("Salim Benfarhat", "xxxxx"),
]


def _redact_string(value: str) -> str:
    result = _IPV4_RE.sub("xxxxx", value)
    result = _IPV6_RE.sub("xxxxx", result)
    for old, new in _STRING_REPLACEMENTS:
        result = result.replace(old, new)
    return result


def _walk(obj):
    """Parcourt récursivement le JSON et applique les remplacements."""
    if isinstance(obj, str):
        return _redact_string(obj)
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _walk(val) for key, val in obj.items()}
    return obj


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process(entries: list[dict]) -> list[dict]:
    cleaned = [e for e in entries if not _should_delete(e)]
    cleaned = _walk(cleaned)
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="Filtre les publications Facebook.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    json_path = args.json
    if not json_path.exists():
        print(f"Fichier introuvable : {json_path}", file=sys.stderr)
        sys.exit(1)

    with json_path.open("r", encoding="utf-8") as f:
        entries = json.load(f)

    before = len(entries)
    cleaned = process(entries)
    after = len(cleaned)
    removed = before - after

    out_path = json_path.with_stem(json_path.stem + "_filtered")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"Avant : {before}  |  Après : {after}  |  Supprimées : {removed}")
    print(f"Fichier écrit : {out_path}")


if __name__ == "__main__":
    main()
