from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from urllib import error, request

from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


DEFAULT_JSON_PATH = Path("your_posts__check_ins__photos_and_videos_1.json")
DEFAULT_INDEX_PATH = Path("rag_index.pkl")


@dataclass
class Chunk:
    chunk_id: str
    post_id: int
    timestamp: int | None
    iso_date: str | None
    title: str
    source: str
    text: str
    url: str | None
    media_uri: str | None


def repair_text(value: str) -> str:
    if not isinstance(value, str):
        return value

    repaired = value
    for _ in range(2):
        if "Ã" not in repaired and "ð" not in repaired:
            break
        try:
            candidate = repaired.encode("latin1").decode("utf-8")
        except UnicodeError:
            break
        if candidate == repaired:
            break
        repaired = candidate

    repaired = repaired.replace("\u0000", " ")
    repaired = re.sub(r"\s+", " ", repaired).strip()
    return repaired


def safe_get_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_get_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def extract_post_texts(entry: dict[str, Any]) -> tuple[list[str], dict[str, str | None]]:
    texts: list[str] = []
    url: str | None = None
    media_uri: str | None = None

    title = repair_text(str(entry.get("title", "")))
    if title:
        texts.append(f"Titre: {title}")

    for data_item in safe_get_list(entry.get("data")):
        data_item = safe_get_dict(data_item)
        post_text = repair_text(str(data_item.get("post", "")))
        if post_text:
            texts.append(f"Post: {post_text}")

    for attachment in safe_get_list(entry.get("attachments")):
        attachment = safe_get_dict(attachment)
        for attachment_data in safe_get_list(attachment.get("data")):
            attachment_data = safe_get_dict(attachment_data)

            external_context = safe_get_dict(attachment_data.get("external_context"))
            external_url = repair_text(str(external_context.get("url", "")))
            external_name = repair_text(str(external_context.get("name", "")))
            if external_name:
                texts.append(f"Contexte externe: {external_name}")
            if external_url:
                url = url or external_url
                texts.append(f"URL: {external_url}")

            media = safe_get_dict(attachment_data.get("media"))
            media_title = repair_text(str(media.get("title", "")))
            media_description = repair_text(str(media.get("description", "")))
            media_uri_value = repair_text(str(media.get("uri", "")))
            if media_title:
                texts.append(f"Media: {media_title}")
            if media_description:
                texts.append(f"Description media: {media_description}")
            if media_uri_value:
                media_uri = media_uri or media_uri_value
                texts.append(f"Fichier media: {media_uri_value}")

            for key in ("name", "description"):
                nested_value = repair_text(str(attachment_data.get(key, "")))
                if nested_value:
                    texts.append(f"{key.capitalize()}: {nested_value}")

    deduped: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = text.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)

    return deduped, {"url": url, "media_uri": media_uri}


def chunk_text(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(entries: list[dict[str, Any]]) -> list[Chunk]:
    chunks: list[Chunk] = []

    for post_id, entry in enumerate(entries):
        texts, metadata = extract_post_texts(entry)
        if not texts:
            continue

        timestamp = entry.get("timestamp")
        iso_date = None
        if isinstance(timestamp, int):
            iso_date = datetime.fromtimestamp(timestamp, tz=UTC).isoformat()

        title = repair_text(str(entry.get("title", "")))
        source = "json_post"
        full_text = "\n".join(texts)

        for index, piece in enumerate(chunk_text(full_text)):
            chunks.append(
                Chunk(
                    chunk_id=f"post-{post_id}-chunk-{index}",
                    post_id=post_id,
                    timestamp=timestamp if isinstance(timestamp, int) else None,
                    iso_date=iso_date,
                    title=title,
                    source=source,
                    text=piece,
                    url=metadata["url"],
                    media_uri=metadata["media_uri"],
                )
            )

    return chunks


def load_entries(json_path: Path) -> list[dict[str, Any]]:
    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Le fichier JSON doit contenir une liste d'objets.")
    return [safe_get_dict(item) for item in data]


def build_index(json_path: Path, index_path: Path) -> None:
    entries = load_entries(json_path)
    chunks = build_chunks(entries)
    if not chunks:
        raise ValueError("Aucun texte exploitable n'a ete extrait du JSON.")

    vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(chunk.text for chunk in chunks)

    payload = {
        "json_path": str(json_path),
        "vectorizer": vectorizer,
        "matrix": matrix,
        "chunks": [asdict(chunk) for chunk in chunks],
    }

    with index_path.open("wb") as handle:
        pickle.dump(payload, handle)

    print(
        f"Index cree: {index_path} | posts={len(entries)} | chunks={len(chunks)}",
        file=sys.stdout,
    )


def load_index(index_path: Path) -> dict[str, Any]:
    with index_path.open("rb") as handle:
        return pickle.load(handle)


def retrieve(index_data: dict[str, Any], question: str, top_k: int) -> list[dict[str, Any]]:
    vectorizer: TfidfVectorizer = index_data["vectorizer"]
    matrix = index_data["matrix"]
    query_vector = vectorizer.transform([repair_text(question)])
    scores = linear_kernel(query_vector, matrix).flatten()

    best_indices = scores.argsort()[::-1][:top_k]
    results: list[dict[str, Any]] = []
    for idx in best_indices:
        score = float(scores[idx])
        if score <= 0:
            continue
        chunk = index_data["chunks"][idx]
        results.append({"score": score, **chunk})
    return results


def build_prompt(
    question: str,
    contexts: list[dict[str, Any]],
    history: list[tuple[str, str]] | None = None,
) -> str:
    context_blocks = []
    for rank, item in enumerate(contexts, start=1):
        block = [
            f"[Contexte {rank}]",
            f"Titre: {item['title'] or 'Sans titre'}",
            f"Date: {item['iso_date'] or 'inconnue'}",
            f"URL: {item['url'] or 'aucune'}",
            f"Texte: {item['text']}",
        ]
        context_blocks.append("\n".join(block))

    lines = [
        "Tu reponds en francais uniquement a partir du contexte fourni. "
        "Si l'information manque, dis-le explicitement."
    ]
    if history:
        lines.append("\nHistorique recent de la conversation:")
        for user_question, assistant_answer in history:
            lines.append(f"Utilisateur: {user_question}")
            lines.append(f"Assistant: {assistant_answer}")
    lines.append(f"\nQuestion: {question}")
    lines.append("\nContexte:\n" + "\n\n".join(context_blocks))
    return "\n".join(lines)


def ask_ollama(prompt: str, model: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
    ).encode("utf-8")

    req = request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(
            "Impossible de joindre Ollama sur http://127.0.0.1:11434. "
            "Lance Ollama ou utilise --llm none."
        ) from exc

    answer = payload.get("response", "")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama a retourne une reponse vide.")
    return answer.strip()


def format_results(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for rank, item in enumerate(results, start=1):
        lines.append(f"Resultat {rank} | score={item['score']:.4f}")
        lines.append(f"Titre: {item['title'] or 'Sans titre'}")
        lines.append(f"Date: {item['iso_date'] or 'inconnue'}")
        if item["url"]:
            lines.append(f"URL: {item['url']}")
        if item["media_uri"]:
            lines.append(f"Media: {item['media_uri']}")
        lines.append(item["text"])
        lines.append("")
    return "\n".join(lines).strip()


def answer_once(
    index_data: dict[str, Any],
    question: str,
    top_k: int,
    llm: str,
    model: str,
    show_sources: bool = True,
    history: list[tuple[str, str]] | None = None,
) -> str | None:
    results = retrieve(index_data, question, top_k=top_k)
    if not results:
        print("Aucun contexte pertinent trouve.", file=sys.stdout)
        return None

    if llm == "none":
        print(format_results(results), file=sys.stdout)
        return None

    prompt = build_prompt(question, results, history=history)
    answer = ask_ollama(prompt, model=model)
    print(answer, file=sys.stdout)
    if show_sources:
        print("\nSources:\n", file=sys.stdout)
        print(format_results(results), file=sys.stdout)
    return answer


def answer_question(
    index_path: Path,
    question: str,
    top_k: int,
    llm: str,
    model: str,
) -> None:
    index_data = load_index(index_path)
    answer_once(index_data, question, top_k, llm, model)


def chat(
    index_path: Path,
    json_path: Path,
    top_k: int,
    llm: str,
    model: str,
    show_sources: bool = True,
) -> None:
    if not index_path.exists():
        print(f"Index absent, construction de {index_path} ...", file=sys.stdout)
        build_index(json_path, index_path)
    index_data = load_index(index_path)

    print("=== Chatbot de tes publications Facebook ===", file=sys.stdout)
    print("Pose une question, ou utilise une commande :", file=sys.stdout)
    print("  /llm ollama|none | /model <nom> | /top-k <n> | /sources on|off", file=sys.stdout)
    print("  /clear | /help | /quit", file=sys.stdout)
    print(f"Mode actuel : llm={llm}, model={model}, top-k={top_k}, sources={'on' if show_sources else 'off'}", file=sys.stdout)
    print("", file=sys.stdout)

    history: list[tuple[str, str]] = []
    while True:
        try:
            raw_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stdout)
            break
        if not raw_input:
            continue

        if raw_input.startswith("/"):
            command, _, argument = raw_input.partition(" ")
            argument = argument.strip()
            lowered = command.lower()
            if lowered in ("/quit", "/exit"):
                print("Au revoir !", file=sys.stdout)
                break
            if lowered == "/help":
                print(
                    "Commandes :\n"
                    "  /llm ollama|none  active ou coupe la generation par Ollama\n"
                    "  /model <nom>      choisit le modele Ollama (ex: gemma4)\n"
                    "  /top-k <n>        nombre de contextes recuperes\n"
                    "  /sources on|off   affiche ou masque les sources apres la reponse\n"
                    "  /clear            efface l'historique de conversation\n"
                    "  /quit             quitte le chatbot",
                    file=sys.stdout,
                )
                continue
            if lowered == "/llm":
                if argument in ("none", "ollama"):
                    llm = argument
                    print(f"Mode LLM : {llm}", file=sys.stdout)
                else:
                    print("Utilisation : /llm none|ollama", file=sys.stdout)
                continue
            if lowered == "/model":
                if argument:
                    model = argument
                    print(f"Modele : {model}", file=sys.stdout)
                else:
                    print("Utilisation : /model <nom>", file=sys.stdout)
                continue
            if lowered == "/top-k":
                try:
                    top_k = int(argument)
                    if top_k < 1:
                        raise ValueError
                    print(f"top-k : {top_k}", file=sys.stdout)
                except ValueError:
                    print("Utilisation : /top-k <nombre positif>", file=sys.stdout)
                continue
            if lowered == "/sources":
                if argument == "on":
                    show_sources = True
                    print("Sources : affichees", file=sys.stdout)
                elif argument == "off":
                    show_sources = False
                    print("Sources : masquees", file=sys.stdout)
                else:
                    print("Utilisation : /sources on|off", file=sys.stdout)
                continue
            if lowered == "/clear":
                history.clear()
                print("Historique efface.", file=sys.stdout)
                continue
            print(f"Commande inconnue : {command}. Tape /help pour la liste.", file=sys.stdout)
            continue

        try:
            answer = answer_once(
                index_data,
                raw_input,
                top_k,
                llm,
                model,
                show_sources=show_sources,
                history=history[-6:],
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stdout)
            continue
        if llm == "ollama" and answer:
            history.append((raw_input, answer))


FRENCH_STOPWORDS = frozenset(
    """un une des le la les de du dans sur avec pour par en au aux et ou mais donc or ni car
    ce cet cette ces mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs
    je tu il elle on nous vous ils elles me te se moi toi lui eux y en
    ai as avais avait avons avez avaient suis es est sommes etes sont etre ete etait etaient
    avoir faire fait faut va aller veux veut peut peux vont seront soyez sois soit devient devenu
    plus moins tres trop bien pas non oui si tout tous toute toutes rien
    quelque quelques comme quand qui que quoi dont ou ici la aussi alors
    apres avant beaucoup encore deja toujours jamais depuis pendant entre vers chez sans
    malgre fois meme autre autres hui aujourd
    post publi publie publier partage partag partager lien profil statut nouvelles nouvelle
    direct message groupe citation publication photos video
    voici salut bonjour ceci cela ceux celle celles
    meme vais juste peu gens ont etre tres voir bon sinon coup com vraiment pense temps
    sais fais moment genre crois dis dit dire aller truc chose choses jour jours an ans
    heure heures monde vie sens sorte plutot besoin envie façon facon suite seule seul
    seul seuls tant tellement assez deux encore autres fois quel quelle quels quelles
    rien nul aucun aucune personne chacun chacune partout nulle tout aussi cela ca franchement
    putain merde oui non peut etre peut-etre partout surtout enfin effectivement davantage
    pourquoi comment ceci cela chez comme alors apres avant pendant puisque tandis voire mais
    hmm euh oh ah bah ben bref exactement certainement certain certaine certaines probablement
    www com http https co fr org net io html php la dans le cas sa si a au ai
    qu l d j n s c ça meme meme même très tres etre être apres après ou où la là voilà deja déjà
    aime reste restent font petit petite peu peut peux temps coup ne pkoi certains certain certe
    mdr hhh lol lool viens venez espère espere meilleurs meilleur meilleure meilleures passe
    """.split()
)

MEDIA_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".m4v", ".webm", ".3gp"})


def classify_post_type(title: str, has_media: bool) -> str:
    lowered = title.lower()
    if "en direct" in lowered:
        return "Vidéo en direct"
    if "photo" in lowered or "vidéo" in lowered or "video" in lowered:
        return "Photo / Vidéo"
    if "lien" in lowered:
        return "Lien partagé"
    if "instagram" in lowered:
        return "Partage Instagram"
    if "actualisé son statut" in lowered:
        return "Actualisation de statut"
    if "partagé une publication" in lowered:
        return "Partage de publication"
    if "partagé un groupe" in lowered:
        return "Partage de groupe"
    if "partagé un profil" in lowered:
        return "Partage de profil"
    if "citation" in lowered:
        return "Citation"
    if "écrit sur" in lowered or "ecrit sur" in lowered:
        return "Message sur profil"
    if has_media:
        return "Photo / Vidéo"
    return "Autre"


def collect_user_texts(entries: list[dict[str, Any]]) -> list[str]:
    user_texts: list[str] = []
    labels = (
        "Post:",
        "Description media:",
        "Media:",
        "Name:",
        "Description:",
        "Contexte externe:",
    )
    for entry in entries:
        texts, _ = extract_post_texts(entry)
        parts: list[str] = []
        for line in texts:
            for label in labels:
                if line.startswith(label):
                    parts.append(line[len(label):].strip())
                    break
        user_texts.append(" ".join(parts))
    return user_texts


def compute_topics(
    entries: list[dict[str, Any]],
    n_topics: int = 8,
    words_per_topic: int = 6,
) -> list[dict[str, Any]]:
    corpus = [text for text in collect_user_texts(entries) if text.strip()]
    if not corpus:
        return []

    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 1),
        min_df=5,
        max_df=0.5,
        stop_words=sorted(FRENCH_STOPWORDS),
    )
    matrix = vectorizer.fit_transform(corpus)
    feature_names = vectorizer.get_feature_names_out()

    model = LatentDirichletAllocation(n_components=n_topics, random_state=42, max_iter=15)
    model.fit(matrix)

    shares = model.transform(matrix).sum(axis=0)
    total = shares.sum() or 1.0
    topics: list[dict[str, Any]] = []
    for topic_index in shares.argsort()[::-1]:
        top_indices = model.components_[topic_index].argsort()[::-1][:words_per_topic]
        words = [str(feature_names[i]) for i in top_indices]
        topics.append(
            {
                "share": float(shares[topic_index] / total),
                "words": words,
                "query": " ".join(words[:4]),
            }
        )
    return topics


def compute_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(entries)
    timestamps: list[int] = []
    months: Counter[str] = Counter()
    post_types: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    media_uris: list[str] = []
    text_entries = 0
    url_entries = 0

    for entry in entries:
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, int):
            timestamps.append(timestamp)
            months[datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m")] += 1

        texts, _ = extract_post_texts(entry)
        if any(line.startswith("Post:") for line in texts):
            text_entries += 1

        has_media = False
        has_url = False
        for attachment in safe_get_list(entry.get("attachments")):
            for attachment_data in safe_get_list(safe_get_dict(attachment).get("data")):
                attachment_data = safe_get_dict(attachment_data)
                context = safe_get_dict(attachment_data.get("external_context"))
                external_url = str(context.get("url", ""))
                if external_url:
                    has_url = True
                    match = re.match(r"https?://([^/]+)", external_url)
                    if match:
                        domains[match.group(1)] += 1
                media = safe_get_dict(attachment_data.get("media"))
                media_uri = str(media.get("uri", ""))
                if media_uri:
                    has_media = True
                    media_uris.append(media_uri)

        if has_url:
            url_entries += 1
        post_types[classify_post_type(str(entry.get("title", "")), has_media)] += 1

    video_count = sum(
        1
        for uri in media_uris
        if Path(uri.lower().split("?")[0]).suffix in MEDIA_VIDEO_SUFFIXES
    )

    first_iso = (
        datetime.fromtimestamp(min(timestamps), tz=UTC).strftime("%Y-%m-%d") if timestamps else "inconnue"
    )
    last_iso = (
        datetime.fromtimestamp(max(timestamps), tz=UTC).strftime("%Y-%m-%d") if timestamps else "inconnue"
    )

    return {
        "total": total,
        "first_iso": first_iso,
        "last_iso": last_iso,
        "months": dict(sorted(months.items())),
        "types": post_types,
        "domains": domains,
        "text_entries": text_entries,
        "url_entries": url_entries,
        "media_total": len(media_uris),
        "media_photos": len(media_uris) - video_count,
        "media_videos": video_count,
    }


def print_stats(stats: dict[str, Any], topics: list[dict[str, Any]]) -> None:
    total = stats["total"]

    def pct(part: int) -> str:
        return f"({part / total * 100:.1f}%)" if total else "(0%)"

    lines: list[str] = []
    lines.append("=== Vue d'ensemble ===")
    lines.append(f"Total de publications : {total}")
    lines.append(f"Période                : {stats['first_iso']} → {stats['last_iso']}")
    lines.append(f"Avec texte             : {stats['text_entries']} {pct(stats['text_entries'])}")
    lines.append(
        f"Avec média             : {stats['media_total']} {pct(stats['media_total'])}"
        f"  [photos {stats['media_photos']}, vidéos {stats['media_videos']}]"
    )
    lines.append(f"Avec lien externe      : {stats['url_entries']} {pct(stats['url_entries'])}")
    lines.append("")

    lines.append("=== Activité par mois ===")
    max_count = max(stats["months"].values()) or 1
    for month, count in stats["months"].items():
        bar = "█" * round(count / max_count * 20)
        lines.append(f"{month} : {count:5d}  {bar}")
    lines.append("")

    lines.append("=== Types de publications ===")
    for name, count in stats["types"].most_common():
        lines.append(f"{name:<24} : {count}")
    lines.append("")

    lines.append("=== Thèmes récurrents (LDA) ===")
    for index, topic in enumerate(topics, start=1):
        lines.append(f"{index:2d}. {topic['share'] * 100:5.1f}%  {', '.join(topic['words'])}")
    lines.append("")

    lines.append("=== Domaines les plus partagés ===")
    for domain, count in stats["domains"].most_common(10):
        lines.append(f"{domain:<40} : {count}")

    print("\n".join(lines), file=sys.stdout)


def md_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
    )


def format_iso(iso_date: str | None) -> str:
    if not iso_date:
        return "Date inconnue"
    try:
        return datetime.fromisoformat(iso_date).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso_date


def excerpt_text(text: str) -> str:
    kept = [
        line
        for line in text.split("\n")
        if not line.startswith(("Titre:", "URL:", "Fichier media:"))
    ]
    return " ".join(part for part in kept if part).strip()


def build_memory(
    entries: list[dict[str, Any]],
    index_path: Path,
    output_path: Path,
    top_themes: int,
    posts_per_theme: int,
    json_path: Path,
) -> None:
    topics = compute_topics(entries, n_topics=top_themes)
    if not topics:
        raise ValueError("Aucun thème à exporter.")

    if not index_path.exists():
        print(f"Index absent, construction de {index_path} ...", file=sys.stdout)
        build_index(json_path, index_path)
    index_data = load_index(index_path)

    stats = compute_stats(entries)
    lines: list[str] = []
    lines.append("# Ma mémoire Facebook")
    lines.append("")
    lines.append(
        f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} à partir de "
        f"{stats['total']} publications ({stats['first_iso']} → {stats['last_iso']}).*"
    )
    lines.append("")

    for topic in topics:
        results = retrieve(index_data, topic["query"], top_k=posts_per_theme * 5)
        seen_posts: set[int] = set()
        picked: list[dict[str, Any]] = []
        for item in results:
            post_id = item["post_id"]
            if post_id in seen_posts:
                continue
            seen_posts.add(post_id)
            picked.append(item)
            if len(picked) >= posts_per_theme:
                break

        label = topic["words"][0]
        lines.append(f"## {label.capitalize()} — {', '.join(topic['words'])}")
        lines.append(f"_{topic['share'] * 100:.1f}% des posts_")
        lines.append("")
        if not picked:
            lines.append("_Aucun post associé trouvé._")
            lines.append("")
            continue
        for item in picked:
            lines.append(f"### {format_iso(item['iso_date'])}")
            lines.append("")
            if item["title"]:
                lines.append(f"**Titre :** {md_escape(item['title'])}")
            lines.append(
                f"**Type :** {classify_post_type(item['title'] or '', bool(item.get('media_uri')))}"
            )
            if item["url"]:
                lines.append(f"**Lien :** {item['url']}")
            if item["media_uri"]:
                lines.append(f"**Média :** {item['media_uri']}")
            lines.append("")
            lines.append(f"> {md_escape(excerpt_text(item['text']))}")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Mémoire exportée : {output_path} ({len(topics)} thèmes)",
        file=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG minimal sur un export JSON de posts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Construit l'index de recherche.")
    build_parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    build_parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)

    ask_parser = subparsers.add_parser("ask", help="Pose une question au RAG.")
    ask_parser.add_argument("question", type=str)
    ask_parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    ask_parser.add_argument("--top-k", type=int, default=5)
    ask_parser.add_argument("--llm", choices=("none", "ollama"), default="none")
    ask_parser.add_argument("--model", type=str, default="mistral")

    chat_parser = subparsers.add_parser(
        "chat", help="Lance un chatbot interactif sur tes publications."
    )
    chat_parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    chat_parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    chat_parser.add_argument("--top-k", type=int, default=5)
    chat_parser.add_argument("--llm", choices=("none", "ollama"), default="none")
    chat_parser.add_argument("--model", type=str, default="mistral")

    stats_parser = subparsers.add_parser("stats", help="Affiche des statistiques sur les publications.")
    stats_parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    stats_parser.add_argument("--top-themes", type=int, default=8, help="Nombre de thèmes LDA à extraire.")

    memory_parser = subparsers.add_parser(
        "memory", help="Exporte une mémoire Markdown des posts classés par thème."
    )
    memory_parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    memory_parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    memory_parser.add_argument("--output", type=Path, default=Path("memory.md"))
    memory_parser.add_argument("--top-themes", type=int, default=8, help="Nombre de thèmes LDA à exporter.")
    memory_parser.add_argument("--posts-per-theme", type=int, default=3)

    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.command == "build":
        build_index(args.json, args.index)
        return
    if args.command == "ask":
        answer_question(args.index, args.question, args.top_k, args.llm, args.model)
        return
    if args.command == "chat":
        chat(args.index, args.json, args.top_k, args.llm, args.model)
        return
    if args.command == "stats":
        entries = load_entries(args.json)
        stats = compute_stats(entries)
        topics = compute_topics(entries, n_topics=args.top_themes)
        print_stats(stats, topics)
        return
    if args.command == "memory":
        entries = load_entries(args.json)
        build_memory(entries, args.index, args.output, args.top_themes, args.posts_per_theme, args.json)
        return
    raise ValueError(f"Commande inconnue: {args.command}")


if __name__ == "__main__":
    main()