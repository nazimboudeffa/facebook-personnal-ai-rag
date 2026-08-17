# Technologies utilisées

Le projet est volontairement minimaliste : **un seul fichier Python, une seule dépendance tierce**. Tout le reste vient de la bibliothèque standard.

## Vue d'ensemble

| Technologie | Rôle dans le projet |
| --- | --- |
| Python 3.10+ | Langage. Types optionnels (`int \| None`), dataclasses, `pathlib`, `typing`. |
| Bibliothèque standard | Parsing, fichiers, dates, HTTP, ligne de commande. |
| scikit-learn (`TfidfVectorizer`) | Indexation lexicale et recherche (retrieval). |
| scikit-learn (`LatentDirichletAllocation`) | Extraction des thèmes récurrents (modèle de sujets). |
| scikit-learn (`linear_kernel`) | Calcul de similarité cosinus entre question et corpus. |
| `pickle` (standard) | Sérialisation de l'index dans `rag_index.pkl`. |
| Ollama (API HTTP) | Génération de réponses en français (optionnelle). |

## 1. Python et bibliothèque standard

Aucun framework, le script est un pur outil CLI. Les morceaux de la bibliothèque standard utilisés :

| Module | Utilisation |
| --- | --- |
| `argparse` | Définition des sous-commandes `build`, `ask`, `chat`, `stats`, `memory` et de leurs options. |
| `json` | Chargement de l'export Facebook et encodage des requêtes vers Ollama. |
| `pickle` | Sauvegarde / rechargement de l'index (`dump` / `load`). |
| `re` | Réparation du texte (`\s+`, caractères nuls) et extraction des domaines d'URL. |
| `collections.Counter` | Comptage des posts par mois, par type, par domaine. |
| `dataclasses` | Modèle `Chunk` : chaque morceau de texte indexé avec ses métadonnées. |
| `datetime` | Conversion des timestamps Unix en dates ISO et en dates lisibles. |
| `pathlib.Path` | Chemins de fichiers. |
| `urllib.request` | Appel HTTP vers l'API d'Ollama. |
| `typing.Any` | Accès sans contrainte aux structures JSON libres. |

## 2. scikit-learn

C'est la seule dépendance externe (`requirements.txt`) :

```text
scikit-learn>=1.5,<2.0
```

### TfidfVectorizer — la recherche lexicale

Utilisé **deux fois**, avec des réglages différents :

**a) Pour l'index de recherche** (`build_index`) :

```python
vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
matrix = vectorizer.fit_transform(chunk.text for chunk in chunks)
```

- `ngram_range=(1, 2)` : indexe les mots simples **et** les paires de mots consécutifs, pour mieux saisir les expressions (« ia locale », « frise chronologique »).
- `min_df=1` : aucun mot n'est ignoré, même les plus rares.

L'index TF-IDF donne un **poids** à chaque terme : un mot est d'autant plus important pour un chunk qu'il y est fréquent (fréquence du terme) et rare dans le reste du corpus (fréquence documentaire inverse). C'est ce qui permet de retrouver les passages les plus « spécifiques ».

**b) Pour l'extraction de thèmes** (`compute_topics`) :

```python
vectorizer = TfidfVectorizer(
    lowercase=True,
    ngram_range=(1, 1),
    min_df=5,
    max_df=0.5,
    stop_words=sorted(FRENCH_STOPWORDS),
)
```

- Unigrammes uniquement (les paires de mots brouillent le modèle de sujets).
- `min_df=5` : ignore les mots présents dans moins de 5 posts (le bruit).
- `max_df=0.5` : ignore les mots présents dans plus de la moitié des posts (les mots outils).
- `stop_words` : une liste manuelle de mots français vides (voir la section dédiée).

### linear_kernel — la similarité

Pour répondre à une question, on vectorise la question avec le **même** vectoriseur que l'index, puis on mesure la proximité avec chaque chunk :

```python
query_vector = vectorizer.transform([repair_text(question)])
scores = linear_kernel(query_vector, matrix).flatten()
best_indices = scores.argsort()[::-1][:top_k]
```

`linear_kernel` calcule le produit scalaire entre des vecteurs TF-IDF normalisés, ce qui revient à une **similarité cosinus** : plus le score est proche de 1, plus le chunk est proche de la question. Les `top-k` meilleurs chunks sont renvoyés avec leur score.

### LatentDirichletAllocation — les thèmes

Pour trouver les thèmes récurrents sans connaître les sujets à l'avance, le projet entraîne un modèle de sujets (LDA) sur les textes des posts :

```python
model = LatentDirichletAllocation(n_components=n_topics, random_state=42, max_iter=15)
model.fit(matrix)
```

LDA suppose que chaque post est un mélange de quelques « sujets » latents, et que chaque sujet est une distribution sur les mots. Une fois entraîné :

- `model.components_[i]` donne les mots les plus représentatifs du sujet `i` (utilisés pour l'afficher) ;
- `model.transform(matrix)` donne le mélange de sujets de chaque post, dont on somme pour estimer la part de chaque thème (`share`).

C'est ce qui fait ressortir des thèmes comme « IA / Ollama / téléchargements mobiles », « France / Algérie / religion », « football / paris », etc.

### Les mots « vides » français

Une constante `FRENCH_STOPWORDS` regroupe des centaines de mots fréquents du français (articles, pronoms, conjonctions, mots de conversation, argot et verlan : `mdr`, `pkoi`, `wsh`…) ainsi que les formes accentuées et non accentuées (`être`/`etre`, `après`/`apres`). Elle sert à nettoyer le vocabulaire avant l'extraction de thèmes.

## 3. pickling — l'index persistant

L'index est sérialisé en binaire avec `pickle` :

```python
payload = {
    "json_path": str(json_path),
    "vectorizer": vectorizer,
    "matrix": matrix,
    "chunks": [asdict(chunk) for chunk in chunks],
}
with index_path.open("wb") as handle:
    pickle.dump(payload, handle)
```

Le fichier `rag_index.pkl` contient donc **tout ce qu'il faut pour répondre sans relire le JSON** : le vectoriseur entraîné, la matrice TF-IDF et les chunks avec leurs métadonnées. C'est ce qui rend les commandes `ask` et `chat` instantanées après un `build`.

## 4. Ollama — la génération

Ollama est un serveur qui fait tourner des modèles de langage en local. Le projet l'appelle via son API HTTP simple, sans SDK :

```python
req = request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
```

La génération est optionnelle (`--llm none` par défaut). Si le serveur n'est pas joignable, une erreur explicite est levée et, dans le chatbot, la session continue.

## Ce qui n'est pas utilisé

- **Pas de base de données** : l'index est un simple fichier pickle, la matrice vit en mémoire.
- **Pas de framework web** : l'interface est le terminal.
- **Pas de SDK client** (ni pour Ollama, ni pour l'IA) : tout passe par HTTP brut ou la bibliothèque standard.
- **Pas d'embeddings** : la recherche est lexicale (TF-IDF), pas sémantique. C'est la piste d'amélioration principale mentionnée dans `projet.md`.
