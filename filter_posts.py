"""Filtre les publications Facebook : suppression et remplacement d'éléments sensibles.

Les règles sont lues depuis filter_rules.txt.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_JSON = Path("data/your_posts__check_ins__photos_and_videos_1.json")
DEFAULT_RULES = Path("filter_rules.txt")

# ── Lecture du fichier de règles ──────────────────────────────────────────────


def load_rules(rules_path: Path) -> tuple[list[re.Pattern], list[re.Pattern]]:
    delete_patterns: list[re.Pattern] = []
    replace_patterns: list[re.Pattern] = []
    current_section: str | None = None

    for raw_line in rules_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[delete]":
            current_section = "delete"
            continue
        if line == "[replace]":
            current_section = "replace"
            continue
        if current_section is None:
            continue

        line = line.encode("utf-8").decode("unicode_escape")
        pattern = re.compile(re.escape(line), re.IGNORECASE)
        if current_section == "delete":
            delete_patterns.append(pattern)
        elif current_section == "replace":
            replace_patterns.append(pattern)

    return delete_patterns, replace_patterns


# ── Filtrage ──────────────────────────────────────────────────────────────────

_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_IPV6_RE = re.compile(r"\b[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}\b")
_MENTION_RE = re.compile(r"@\[[^\]]*\]")


def _should_delete(entry: dict, delete_patterns: list[re.Pattern]) -> bool:
    title = entry.get("title", "")
    return any(p.search(title) for p in delete_patterns)


def _redact_string(value: str, replace_patterns: list[re.Pattern]) -> str:
    result = _MENTION_RE.sub("xxxxx", value)
    for pattern in replace_patterns:
        result = pattern.sub("xxxxx", result)
    result = _IPV4_RE.sub("xxxxx", result)
    result = _IPV6_RE.sub("xxxxx", result)
    return result


def _walk(obj, replace_patterns: list[re.Pattern]):
    if isinstance(obj, str):
        return _redact_string(obj, replace_patterns)
    if isinstance(obj, list):
        return [_walk(item, replace_patterns) for item in obj]
    if isinstance(obj, dict):
        return {key: _walk(val, replace_patterns) for key, val in obj.items()}
    return obj


# ── Pipeline ──────────────────────────────────────────────────────────────────


def process(
    entries: list[dict],
    delete_patterns: list[re.Pattern],
    replace_patterns: list[re.Pattern],
) -> list[dict]:
    cleaned = [e for e in entries if not _should_delete(e, delete_patterns)]
    cleaned = _walk(cleaned, replace_patterns)
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="Filtre les publications Facebook.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    if not args.json.exists():
        print(f"Fichier introuvable : {args.json}", file=sys.stderr)
        sys.exit(1)
    if not args.rules.exists():
        print(f"Fichier de règles introuvable : {args.rules}", file=sys.stderr)
        sys.exit(1)

    delete_patterns, replace_patterns = load_rules(args.rules)
    print(
        f"Règles chargées : {len(delete_patterns)} suppression(s), "
        f"{len(replace_patterns)} remplacement(s)"
    )

    with args.json.open("r", encoding="utf-8") as f:
        entries = json.load(f)

    before = len(entries)
    cleaned = process(entries, delete_patterns, replace_patterns)
    after = len(cleaned)
    removed = before - after

    out_path = args.json.with_stem(args.json.stem + "_filtered")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"Avant : {before}  |  Après : {after}  |  Supprimées : {removed}")
    print(f"Fichier écrit : {out_path}")


if __name__ == "__main__":
    main()
