# Le projet

## Objectif

Transformer un export JSON brut de publications Facebook en un moteur de recherche et de questions-réponses **100 % local**, puis en un outil d'analyse et de synthèse personnelle.

Le projet répond à des questions du type :

- « Quels posts parlent d'Ollama ? »
- « Montre-moi les publications où je parle d'IA locale »
- « Fais-moi un résumé de ce que je publie le plus souvent »
- « Quels sujets reviennent le plus souvent dans mes publications ? »

## Les données

Le fichier source est l'export Facebook standard nommé
`your_posts__check_ins__photos_and_videos_1.json`. Il contient **5 539 entrées** (posts, photos, liens, vidéos en direct, check-ins…).

Chaque entrée est un objet JSON avec quatre champs :

| Champ | Description |
| --- | --- |
| `timestamp` | Date de publication (epoch Unix en secondes). |
| `title` | Libellé généré par Facebook (« Naz LeDuc a partagé un lien. »). |
| `data` | Liste de dictionnaires ; le champ `post` contient le texte rédigé par l'utilisateur. |
| `attachments` | Liste de pièces jointes : liens externes (`external_context`), médias (`media` avec titre, description, uri), nom/description de contenu partagé. |

Quelques chiffres sur le jeu de données actuel :

- 5 539 publications sur la période 2025-10-24 → 2026-08-05 ;
- 61,5 % des posts contiennent du texte rédigé ;
- 44,5 % contiennent un média (photos et vidéos) ;
- 34 % partagent un lien externe (YouTube, TikTok, GitHub, Notion…).

## Le pipeline

Le projet suit un pipeline RAG (Retrieval-Augmented Generation) classique, découpé en étapes :

```
JSON Facebook
    │  1. Chargement
    ▼
Entrées (dict)
    │  2. Filtrage (filter_posts.py) — suppressions + remplacements
    ▼
JSON filtré (data/*_filtered.json)
    │  3. Extraction des textes utiles + réparation de l'encodage
    ▼
Textes par post
    │  4. Découpage en chunks
    ▼
Chunks
    │  5. Indexation TF-IDF (fit) / vectorisation (transform)
    ▼
Index TF-IDF (matrice)  ────────────►  rag_index.pkl
    │
    │  6. Requête : vectorisation + similarité cosinus
    ▼
Top-k chunks pertinents
    │  7. Prompt = question + contexte (+ historique éventuel)
    ▼
    ├── LLM désactivé  → affichage brut des passages trouvés
    └── Ollama local   → réponse rédigée en français
```

### 1. Chargement

`load_entries()` lit le JSON en UTF-8, vérifie que c'est une liste, et assainit chaque élément avec `safe_get_dict()` pour ne jamais faire planter le script sur une structure inattendue.

### 2. Filtrage

`filter_posts.py` est un script séparé qui lit les règles depuis `filter_rules.txt` et applique deux types d'opérations sur le JSON brut :

- **Suppressions** (`[delete]`) : un post est entièrement supprimé si son titre matche un des motifs.
- **Remplacements** (`[replace]`) : les chaînes correspondantes sont remplacées par `xxxxx` dans toutes les valeurs du JSON (récursivement).

Les tags `@[...]` (mentions Facebook) et les adresses IP (IPv4/IPv6) sont toujours remplacés automatiquement, indépendamment du fichier de règles.

La recherche est insensible à la casse. Les séquences `\uXXXX` dans le fichier de règles sont décodées automatiquement.

### 3. Extraction et nettoyage

`extract_post_texts()` transforme chaque entrée en une liste de lignes étiquetées :

```
Titre: Naz LeDuc a partagé un lien.
Post: Je viens de tester Ollama en local...
Contexte externe: github.com/nazimboudeffa/ollama-local-trading
URL: https://github.com/nazimboudeffa/ollama-local-trading
Media: Téléchargements mobiles
Description media: Nouvelle version de mon appli...
Fichier media: your_facebook_activity/posts/media/...
```

Chaque texte passe par `repair_text()`, qui corrige les problèmes d'encodage de l'export (textes « mojibake » du type `partagÃ©` → `partagé`, caractères nuls, espaces multiples).

### 4. Découpage en chunks

Les longs posts sont découpés en morceaux de 700 caractères avec un recouvrement de 120 caractères (`chunk_text()`), pour que la recherche et le LLM reçoivent des blocs de taille raisonnable.

### 5. Indexation

`build_index()` entraîne un `TfidfVectorizer` sur tous les chunks, produit une matrice TF-IDF, puis sérialise le tout (vectoriseur + matrice + chunks) dans `rag_index.pkl` via `pickle`.

### 6. Recherche

`retrieve()` vectorise la question avec le même vectoriseur, calcule la similarité cosinus (`linear_kernel`) entre la question et tous les chunks, et renvoie les `top-k` plus pertinents avec leur score.

### 7. Génération (optionnelle)

- Sans LLM (`--llm none`) : les passages trouvés sont simplement affichés.
- Avec Ollama (`--llm ollama`) : un prompt est construit (`build_prompt`) avec la question, les extraits et éventuellement l'historique récent de conversation, puis envoyé à l'API locale d'Ollama (`ask_ollama`). La réponse est affichée avec ses sources.

## Ce que le projet sait faire en plus

Le pipeline ci-dessus sert de socle à cinq usages :

- **`filter_posts.py`** — filtrage des données sensibles (suppressions + remplacements) via un fichier de règles déclaratif.
- **`ask`** — une question unique, réponse + sources.
- **`chat`** — une session interactive avec commandes (`/llm`, `/model`, `/top-k`, `/sources`, `/help`, `/quit`).
- **`stats`** — analyse des publications (activité mensuelle, types de posts, thèmes LDA, domaines partagés).
- **`memory`** — export d'une « mémoire » Markdown : pour chaque thème détecté, les posts les plus représentatifs.

## Limites actuelles

- La recherche repose sur **TF-IDF** (lexique) : elle fonctionne sur les mots exacts, pas sur le sens. Des synonymes ou des questions reformulées peuvent passer à côté. Des embeddings (`sentence-transformers`) seraient la prochaine étape naturelle.
- Les **images ne sont pas analysées** : seuls leur titre et leur description sont indexés.
- L'extraction de thèmes (LDA) dépend d'une liste de mots français « vides » manuelle, qui peut laisser passer du bruit (verlan, argot, mots très fréquents).
- Un seul fichier d'export est traité ; un export Facebook complet contient aussi les amis, les réactions, les commentaires, les groupes…
