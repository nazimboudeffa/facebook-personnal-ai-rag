# RAG Python sur ton export JSON

Ce mini-projet construit un index local a partir de `your_posts__check_ins__photos_and_videos_1.json` puis permet de poser des questions dessus.

Le pipeline fait 4 choses:

1. charge le JSON
2. extrait les vrais textes utiles (`post`, `description`, `title`, `url`, `name`)
3. repare une partie du texte mal encode (`partagÃ©` -> `partage`/`partagee` corrige selon le contenu)
4. cree un index TF-IDF pour faire la recherche semantique de base

Une documentation complète est disponible dans le dossier [doc/](doc/) : présentation du projet, technologies utilisées, architecture et guide d'utilisation.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Construire l'index

```powershell
python rag_posts.py build
```

Tu obtiendras un fichier `rag_index.pkl`.

## Statistiques des publications

```powershell
python rag_posts.py stats
```

Affiche une vue d'ensemble (total, période, texte/média/liens), l'activité par mois, les types de publications, les thèmes récurrents (extraits par un modèle LDA) et les domaines les plus partagés.

Tu peux ajuster le nombre de thèmes avec `--top-themes` (8 par défaut).

## Exporter une "mémoire" en Markdown

```powershell
python rag_posts.py memory
```

Génère `memory.md` : pour chaque thème récurrent, les posts les plus représentatifs avec leur date, type, lien et extrait. Options utiles :

```powershell
python rag_posts.py memory --top-themes 12 --posts-per-theme 5 --output mes_souvenirs.md
```

Si l'index `rag_index.pkl` est absent, il sera construit automatiquement.

## Générer des blog posts

```powershell
python rag_posts.py blog
```

Génère des articles de blog en Markdown à partir de tes publications Facebook via Ollama. Le script détecte automatiquement les thèmes récurrents (LDA), récupère les posts associés, puis demande à Ollama de rédiger un article structuré pour chaque thème.

Articles exportés dans le dossier `blog_posts/` avec frontmatter YAML (titre, thème, date, sources). Les métadonnées des publications sources (post_id, date, titre, URL, score) sont incluses directement dans le frontmatter `sources:` de chaque fichier, et une section `## Sources` lisible est ajoutée en bas de l'article.

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
python rag_posts.py blog --topics "intelligence artificielle" "cybersécurité" "trading" --single --model gemma4
```

Options :

```
--model <nom>            modèle Ollama (défaut : mistral)
--top-themes <n>         nombre de thèmes à transformer en articles (défaut : 5)
--posts-per-theme <n>    nombre de posts récupérés par thème (défaut : 4)
--output-dir <dossier>   dossier de sortie (défaut : blog_posts/)
--topics <t1> <t2> ...   thèmes personnalisés (désactive la détection LDA)
--single                 fusionne tous les topics en un seul article
```

## Chatbot interactif

```powershell
python rag_posts.py chat
```

Pose des questions en continu sur tes publications. Sans Ollama, il affiche les passages les plus pertinents ; avec Ollama, il genere une vraie reponse en francais. Si l'index `rag_index.pkl` est absent, il est construit automatiquement.

Commandes disponibles dans le chat :

```
/llm ollama|none     active ou coupe la generation par Ollama
/model <nom>         choisit le modele Ollama (ex: gemma4)
/top-k <n>           nombre de contextes recuperes
/sources on|off      affiche ou masque les sources apres la reponse
/clear               efface l'historique de conversation
/help                liste des commandes
/quit                quitter
```

Exemple de session :

```powershell
python rag_posts.py chat --llm ollama --model gemma4
> Quels sujets je partage le plus souvent ?
> Et entre 2023 et 2024 ?
> /sources off
> Parle-moi de mon projet de frise France/Algerie
```

## Poser une question sans LLM

```powershell
python rag_posts.py ask "Quels posts parlent d'Ollama ?"
```

Cette commande renvoie les passages les plus pertinents avec leur score.

## Poser une question avec Ollama

Si tu veux un vrai comportement RAG complet (retrieval + generation), installe Ollama puis lance un modele local, par exemple:

```powershell
ollama pull gemma4
python rag_posts.py ask "Quels posts parlent d'Ollama ?" --llm ollama --model gemma4
```

Le script enverra les meilleurs extraits a Ollama pour generer une reponse en francais.

## Exemples de questions

```powershell
python rag_posts.py stats
python rag_posts.py memory --top-themes 10 --posts-per-theme 4
```

```powershell
python rag_posts.py ask "Quels sujets reviennent le plus souvent dans mes publications ?"
python rag_posts.py ask "Quels posts parlent de trading ?"
python rag_posts.py ask "Montre-moi les publications ou je parle d'IA locale" --llm ollama
python rag_posts.py ask "Quels posts parlent d'Ollama, de LLM ou de RAG ?"
python rag_posts.py ask "Retrouve les publications ou je partage un lien externe"
python rag_posts.py ask "Quels posts mentionnent un projet perso ou du code ?"
python rag_posts.py ask "Montre-moi les publications ou je parle d'automatisation ou d'outils IA"
python rag_posts.py ask "Quelles publications semblent etre des check-ins ou des sorties ?"
python rag_posts.py ask "Quels posts contiennent une photo ou une video avec une description ?"
python rag_posts.py ask "Retrouve les publications ou je parle de travail, business ou productivite"
python rag_posts.py ask "Quels themes je mentionne entre 2023 et 2024 ?" --llm ollama
python rag_posts.py ask "Fais-moi un resume de ce que je publie le plus souvent" --llm ollama
```

```powershell
python rag_posts.py blog --model mistral --top-themes 8
python rag_posts.py blog --topics "IA locale" "sécurité" "open source" --model gemma4
python rag_posts.py blog --topics "IA locale" "sécurité" "open source" --single --model gemma4
```

## Limites actuelles

- L'index utilise TF-IDF, donc ce n'est pas aussi fort que des embeddings modernes.
- Les images ne sont pas analysees; seul leur texte associe est utilise.
- Si tu veux une meilleure qualite, l'etape suivante est de remplacer TF-IDF par des embeddings (`sentence-transformers` ou `bge-small`) et de garder la meme structure de code.
