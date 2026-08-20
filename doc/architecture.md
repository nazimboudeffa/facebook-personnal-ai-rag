# Architecture du code

Tout le code tient dans un seul fichier, `rag_posts.py`, organisé en trois zones :

1. **Le cœur RAG** — chargement, nettoyage, découpage, indexation, recherche, génération.
2. **L'analyse** — statistiques, extraction de thèmes (LDA), export « mémoire ».
3. **L'interface CLI** — parsing des arguments et dispatch.

Un script séparé, `filter_posts.py`, gère le filtrage des données sensibles avant indexation.

## Cartographie des fonctions

### Zone RAG (lignes ~24 à 448)

| Fonction | Rôle |
| --- | --- |
| `Chunk` (dataclass) | Un morceau de texte indexé : `chunk_id`, `post_id`, `timestamp`, `iso_date`, `title`, `source`, `text`, `url`, `media_uri`. |
| `repair_text()` | Corrige l'encodage cassé (`partagÃ©` → `partagé`), remplace les caractères nuls, normalise les espaces. |
| `safe_get_list()` / `safe_get_dict()` | Retournent une liste/dict vide si la valeur n'a pas le bon type. Immunise le script contre les structures JSON imprévues. |
| `extract_post_texts()` | Transforme une entrée JSON en lignes étiquetées (`Titre:`, `Post:`, `Media:`…) + métadonnées (`url`, `media_uri`). |
| `chunk_text()` | Découpe un long texte en morceaux de 700 caractères avec 120 de recouvrement. |
| `build_chunks()` | Applique extraction + découpage sur toutes les entrées et fabrique les objets `Chunk`. |
| `load_entries()` | Lit et valide le JSON. |
| `build_index()` | Entraîne le TF-IDF et sérialise l'index dans `rag_index.pkl`. |
| `load_index()` | Recharge l'index depuis le pickle. |
| `retrieve()` | Vectorise la question et renvoie les `top-k` chunks les plus proches (similarité cosinus). Paramètre `min_score` pour filtrer par seuil TF-IDF. |
| `build_prompt()` | Construit le prompt : instructions, historique éventuel, question, contexte. |
| `ask_ollama()` | Appelle l'API locale d'Ollama et retourne la réponse. |
| `format_results()` | Formate les résultats (score, titre, date, URL, média, texte) pour l'affichage. |
| `answer_once()` | Orchestre une réponse : recherche → affichage brut ou prompt + génération. |
| `answer_question()` | Variante non interactive utilisée par la commande `ask`. |
| `chat()` | Boucle interactive : lit les questions et les commandes (`/llm`, `/top-k`…), maintient un historique. |

### Zone analyse (lignes ~450 à 777)

| Fonction | Rôle |
| --- | --- |
| `FRENCH_STOPWORDS` | Constante : mots français vides pour nettoyer le vocabulaire des thèmes. |
| `classify_post_type()` | Déduit le type d'un post depuis son titre (« Photo / Vidéo », « Lien partagé »…). |
| `collect_user_texts()` | Récupère les textes réellement rédigés (hors titres Facebook) par post. |
| `compute_topics()` | Entraîne un modèle LDA et renvoie les thèmes triés par importance (mots + part). |
| `compute_stats()` | Agrège tout : total, période, activité mensuelle, types, domaines, médias, textes, liens. |
| `print_stats()` | Affiche les statistiques et les thèmes dans le terminal. |
| `md_escape()` / `format_iso()` / `excerpt_text()` | Aides au rendu Markdown (échappement, dates lisibles, extraits nettoyés). |
| `build_memory()` | Génère `memory.md` : pour chaque thème, les posts les plus représentatifs. |

### Zone blog (lignes ~780 à 900)

| Fonction | Rôle |
| --- | --- |
| `build_blog_prompt()` | Construit le prompt pour la génération d'un article de blog à partir de posts récupérés. |
| `generate_blog_posts()` | Orchestre la génération : thèmes → retrieve → Ollama → export Markdown avec frontmatter sources. |

### Zone CLI (lignes ~900+)

| Fonction | Rôle |
| --- | --- |
| `parse_args()` | Définit les sous-commandes et leurs options via `argparse`. |
| `main()` | Configure la sortie UTF-8 (Windows) et route vers le bon sous-commande. |

## Script de filtrage — `filter_posts.py`

Script séparé qui lit `filter_rules.txt` et applique des suppressions et remplacements sur le JSON brut avant indexation.

### Fonctions

| Fonction | Rôle |
| --- | --- |
| `load_rules()` | Parse `filter_rules.txt` : lit les sections `[delete]` et `[replace]`, compile les motifs en regex insensibles à la casse. Les séquences `\uXXXX` sont décodées automatiquement. |
| `_should_delete()` | Vérifie si le titre d'une entrée matche un des motifs de suppression. |
| `_redact_string()` | Applique les remplacements dans l'ordre : 1) tags `@[...]` → `xxxxx`, 2) motifs du fichier de règles, 3) adresses IPv4, 4) adresses IPv6. |
| `_walk()` | Parcourt récursivement le JSON (str, list, dict) et applique `_redact_string()` à chaque chaîne. |
| `process()` | Pipeline complet : suppression des posts → remplacements récursifs. |

### Format de `filter_rules.txt`

```ini
# Commentaires et lignes vides ignorés
[delete]
motif1
motif2

[replace]
chaîne à remplacer
```

- Les motifs dans `[delete]` suppriment le **post entier** si le titre matche.
- Les motifs dans `[replace]` remplacent toutes les occurrences par `xxxxx` dans **toutes les valeurs** du JSON.
- Les tags `@[...]` (mentions Facebook) sont toujours remplacés par `xxxxx`, indépendamment du fichier de règles.
- La recherche est **insensible à la casse**.

## Flux de données

### Un point de recherche (`retrieve`)

```
question ──► repair_text ──► vectorizer.transform ──► linear_kernel ──► argsort ──► top-k Chunk
                                │
                          (même vectoriseur que l'index)
```

### Une réponse avec LLM (`answer_once` avec `--llm ollama`)

```
question ──► retrieve (top-k) ──► build_prompt(question, chunks, historique)
                                      │
                                      ▼
                                 ask_ollama ──► Ollama (localhost:11434)
                                      │
                                      ▼
                              réponse + sources affichées
```

### Les statistiques (`stats`)

```
JSON ──► compute_stats ──► stats (dict)
   │          │
   │          └────────────► print_stats
   └──► compute_topics ──► topics (list[dict])
```

### La mémoire (`memory`)

```
JSON ──► compute_topics ──► thèmes
              │
              ▼
    pour chaque thème : retrieve(index, mots du thème) ──► posts dédupliqués par post_id
              │
              ▼
   rédaction Markdown ──► memory.md
```

### Les blog posts (`blog`)

```
JSON ──► compute_topics (ou --topics) ──► thèmes
              │
              ▼
  pour chaque thème (ou tous si --single) :
    retrieve(index, thème, min_score) ──► posts dédupliqués par post_id
              │
              ▼
    build_blog_prompt ──► ask_ollama ──► article Markdown
              │
              ▼
    frontmatter YAML (sources JSON + métadonnées)
    + section ## Sources (liste lisible)
              │
              ▼
    blog_posts/YYYYMMDD_HHMMSS_thème_modèle.md
```

### Le filtrage (`filter_posts.py`)

```
filter_rules.txt ──► load_rules ──► delete_patterns + replace_patterns
                                           │
JSON brut ──► pour chaque entrée :          │
    │                                       │
    ├── _should_delete(titre, delete) ──► supprimer ou garder
    │
    └── _walk(valeurs, replace) ──► pour chaque chaîne :
            │
            ├── @[...] ──► xxxxx
            ├── motifs [replace] ──► xxxxx
            ├── IPv4 ──► xxxxx
            └── IPv6 ──► xxxxx
                    │
                    ▼
            JSON filtré ──► *_filtered.json
```

## Structures de données principales

### Le payload de `rag_index.pkl`

```python
{
    "json_path": str,                 # chemin du JSON source
    "vectorizer": TfidfVectorizer,    # vectoriseur entraîné
    "matrix": scipy.sparse.csr_matrix,# matrice TF-IDF (1 ligne par chunk)
    "chunks": list[dict],             # Chunk sérialisés via dataclasses.asdict
}
```

### Le dict de stats (sortie de `compute_stats`)

```python
{
    "total": int,            # nombre de publications
    "first_iso": str,        # première date (YYYY-MM-DD)
    "last_iso": str,         # dernière date (YYYY-MM-DD)
    "months": dict,          # {"2026-01": 700, ...}
    "types": Counter,        # {"Lien partagé": 1878, ...}
    "domains": Counter,      # {"youtube.com": 458, ...}
    "text_entries": int,     # posts avec texte rédigé
    "url_entries": int,      # posts avec lien externe
    "media_total": int,      # fichiers médias
    "media_photos": int,
    "media_videos": int,
}
```

### Le dict de thème (sortie de `compute_topics`)

```python
{
    "share": float,   # part du corpus attribuée au thème (0..1)
    "words": list,    # mots les plus représentatifs du thème
    "query": str,     # les 4 premiers mots, réutilisés pour retrouver des posts
}
```

## Choix de conception

- **Un seul fichier** : le projet est volontairement un script unique, sans package, pour rester simple à copier/exécuter.
- **`from __future__ import annotations`** : permet les annotations de type modernes (`list[Chunk]`, `str | None`) tout en restant compatible.
- **JSON tolérant** : chaque accès passe par `safe_get_list`/`safe_get_dict`, car un export Facebook réel contient des structures très irrégulières.
- **Réutilisation du pipeline** : le chatbot, la mémoire et les stats reposent tous sur les mêmes fonctions de base (`extract_post_texts`, `retrieve`, `compute_topics`).
- **Sortie UTF-8 forcée** (`sys.stdout.reconfigure`) pour afficher correctement accents, `→` et `█` sous Windows.
