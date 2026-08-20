# Guide d'utilisation

Le script s'utilise en ligne de commande :

```powershell
python rag_posts.py <commande> [options]
```

Les commandes disponibles : `build`, `ask`, `chat`, `stats`, `memory`, `blog`.

## Installation

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 0. `filter_posts.py` — filtrer les données

```powershell
python filter_posts.py
```

Script séparé de `rag_posts.py`. Lit les règles depuis `filter_rules.txt` et applique des suppressions et remplacements sur le JSON brut. Le fichier filtré est écrit à côté de l'original avec le suffixe `_filtered`.

### Fonctionnement

Le fichier `filter_rules.txt` est organisé en deux sections :

```ini
# Commentaires et lignes vides ignorés

[delete]
# Supprime le POST ENTIER si le titre matche (insensible à la casse)
a \u00c3\u00a9crit sur le profil de
a écrit sur le profil de

[replace]
# Remplace la chaîne par xxxxx dans toutes les valeurs du JSON
Salim Benfarhat
```

### Ordre des remplacements

Pour chaque chaîne de caractères dans le JSON, les remplacements s'appliquent dans cet ordre :

1. **Tags `@[...]`** — toutes les mentions Facebook (`@[id:type Nom]`) sont remplacées par `xxxxx`
2. **Motifs `[replace]`** — chaque ligne du fichier de règles est remplacée par `xxxxx`
3. **Adresses IPv4** — tout motif `\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}` est remplacé par `xxxxx`
4. **Adresses IPv6** — tout motif hexadécimal avec deux-points est remplacé par `xxxxx`

L'ordre est important : les tags `@[...]` sont nettoyés en premier pour éviter que les regex IP ne découpent les IDs numériques qu'ils contiennent.

### Ajouter une règle

Il suffit d'ajouter une ligne dans `filter_rules.txt` :

```ini
[delete]
nouveau motif de suppression

[replace]
nouvelle chaîne à anonymiser
```

Pas besoin de toucher au Python. Les séquences `\uXXXX` sont décodées automatiquement.

### Options

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--json <fichier>` | `data/your_posts__check_ins__photos_and_videos_1.json` | Fichier d'entrée. |
| `--rules <fichier>` | `filter_rules.txt` | Fichier de règles. |

### Exemples

```powershell
python filter_posts.py
python filter_posts.py --json data/mon_autre_export.json
python filter_posts.py --rules mes_regles.txt
```

## 1. `build` — construire l'index

```powershell
python rag_posts.py build
```

Lit le JSON, extrait et nettoie les textes, découpe en chunks, entraîne le TF-IDF et écrit `rag_index.pkl`.

Options :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--json <fichier>` | `your_posts__check_ins__photos_and_videos_1.json` | Fichier d'export Facebook. |
| `--index <fichier>` | `rag_index.pkl` | Fichier d'index produit. |

## 2. `ask` — une question ponctuelle

```powershell
python rag_posts.py ask "Quels posts parlent d'Ollama ?"
```

Renvoie les passages les plus pertinents avec leur score. Ajoute `--llm ollama` pour obtenir une réponse rédigée :

```powershell
python rag_posts.py ask "Fais-moi un résumé de ce que je publie le plus souvent" --llm ollama --model gemma4
```

Options :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `question` | — | La question (obligatoire). |
| `--index <fichier>` | `rag_index.pkl` | Index à utiliser. |
| `--top-k <n>` | 5 | Nombre de contextes récupérés. |
| `--llm none\|ollama` | `none` | Active ou non la génération. |
| `--model <nom>` | `mistral` | Modèle Ollama (si `--llm ollama`). |

## 3. `chat` — le chatbot interactif

```powershell
python rag_posts.py chat
python rag_posts.py chat --llm ollama --model gemma4
```

Pose des questions en continu. Si l'index n'existe pas, il est construit automatiquement. L'historique des derniers échanges est réinjecté dans le prompt pour permettre les questions de suivi.

Commandes disponibles pendant la session :

| Commande | Effet |
| --- | --- |
| `/llm ollama\|none` | Active ou coupe la génération par Ollama. |
| `/model <nom>` | Change le modèle Ollama (ex. `gemma4`). |
| `/top-k <n>` | Nombre de contextes récupérés. |
| `/sources on\|off` | Affiche ou masque les sources après la réponse. |
| `/clear` | Efface l'historique de conversation. |
| `/help` | Affiche l'aide des commandes. |
| `/quit` | Quitte le chatbot. |

Mêmes options de lancement que `ask` : `--json`, `--index`, `--top-k`, `--llm`, `--model`.

## 4. `stats` — analyser ses publications

```powershell
python rag_posts.py stats
```

Affiche :

- une vue d'ensemble (total, période, textes, médias, liens) ;
- l'activité par mois (histogramme) ;
- les types de publications (Photo/Vidéo, Lien, Direct…) ;
- les thèmes récurrents extraits par LDA, avec leur part du corpus ;
- les 10 domaines les plus partagés.

Options :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--json <fichier>` | le JSON par défaut | Fichier d'export. |
| `--top-themes <n>` | 8 | Nombre de thèmes LDA à extraire. |

## 5. `memory` — exporter une « mémoire » Markdown

```powershell
python rag_posts.py memory
```

Génère `memory.md` : pour chaque thème détecté, les posts les plus représentatifs avec leur date, type, lien, média et un extrait. Si l'index manque, il est construit automatiquement.

Options :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--json <fichier>` | le JSON par défaut | Fichier d'export. |
| `--index <fichier>` | `rag_index.pkl` | Index utilisé pour retrouver les posts. |
| `--output <fichier>` | `memory.md` | Fichier Markdown de sortie. |
| `--top-themes <n>` | 8 | Nombre de thèmes à exporter. |
| `--posts-per-theme <n>` | 3 | Nombre de posts affichés par thème. |

Exemple :

```powershell
python rag_posts.py memory --top-themes 12 --posts-per-theme 5 --output mes_souvenirs.md
```

## Exemples de questions

```powershell
python rag_posts.py ask "Quels sujets reviennent le plus souvent dans mes publications ?"
python rag_posts.py ask "Quels posts parlent de trading ?"
python rag_posts.py ask "Montre-moi les publications où je parle d'IA locale" --llm ollama
python rag_posts.py ask "Quels posts parlent d'Ollama, de LLM ou de RAG ?"
python rag_posts.py ask "Retrouve les publications où je partage un lien externe"
python rag_posts.py ask "Quels posts mentionnent un projet perso ou du code ?"
python rag_posts.py ask "Quels posts contiennent une photo ou une vidéo avec une description ?"
python rag_posts.py ask "Quels thèmes je mentionne entre 2023 et 2024 ?" --llm ollama
python rag_posts.py stats
python rag_posts.py memory --top-themes 10 --posts-per-theme 4
```

## 6. `blog` — générer des articles de blog

```powershell
python rag_posts.py blog
```

Génère des articles de blog en Markdown à partir de tes publications Facebook via Ollama. Le script détecte les thèmes récurrents (LDA), récupère les posts associés, puis demande à Ollama de rédiger un article structuré pour chaque thème.

Chaque fichier contient un frontmatter YAML (titre, thème, date, score, sources) et une section `## Sources` en fin d'article listant les publications utilisées.

Avec détection automatique des thèmes :

```powershell
python rag_posts.py blog --model gemma4
```

Avec des thèmes personnalisés :

```powershell
python rag_posts.py blog --topics "intelligence artificielle" "cybersécurité" "trading" --model gemma4
```

Un seul article combinant tous les topics :

```powershell
python rag_posts.py blog --topics "intelligence artificielle" "cybersécurité" --single --model gemma4
```

Options :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--json <fichier>` | le JSON par défaut | Fichier d'export. |
| `--index <fichier>` | `rag_index.pkl` | Index utilisé. |
| `--output-dir <dossier>` | `blog_posts/` | Dossier de sortie. |
| `--model <nom>` | `mistral` | Modèle Ollama. |
| `--top-themes <n>` | 5 | Nombre de thèmes à transformer en articles (LDA). |
| `--posts-per-theme <n>` | 4 | Nombre de posts récupérés par thème pour alimenter le contexte. |
| `--topics <t1> <t2> ...` | — | Thèmes personnalisés (désactive la détection LDA). |
| `--single` | désactivé | Fusionne tous les topics en un seul article. |
| `--min-score <n>` | 0.01 | Score TF-IDF minimum pour inclure un post. Baisser pour récupérer plus de posts, augmenter pour n garder que les meilleurs matchs. |

### `--min-score` en détail

Le score TF-IDF mesure à quel point un post correspond à la requête. Il va de **0** (aucune correspondance) à **1** (correspondance parfaite). En pratique sur un export Facebook, les scores pertinents tournent entre 0.01 et 0.3 :

- **0.01 - 0.05** : posts qui matchent faiblement, résultats larges
- **0.05 - 0.1** : correspondances moyennes
- **0.1 - 0.3** : meilleurs résultats, forte similarité
- **> 0.3** : rare, correspondance très précise

Par défaut, `--min-score 0.01` exclut les posts dont le score est inférieur ou égal à 0.01. Pour inclure des posts qui matchent moins fortement :

```powershell
python rag_posts.py blog --topics "IA locale" --min-score 0.001 --model gemma4
```

Pour n garder que les meilleurs résultats :

```powershell
python rag_posts.py blog --topics "IA locale" --min-score 0.05 --model gemma4
```

### Format des fichiers générés

Chaque article est un fichier Markdown unique avec un nom au format `YYYYMMDD_HHMMSS_thème_modèle.md`. Le frontmatter contient les métadonnées des publications sources en JSON pour un accès programmatique :

```yaml
---
title: "Intelligence artificielle"
theme: intelligence, artificielle, local
share: 12.3%
source_posts: 4
generated: 2026-08-19T14:30:22
sources: |
  [
    {"rank": 1, "post_id": 42, "date": "2025-03-15T10:30:00+00:00", ...},
    ...
  ]
---
```
