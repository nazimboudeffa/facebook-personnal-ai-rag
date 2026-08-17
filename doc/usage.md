# Guide d'utilisation

Le script s'utilise en ligne de commande :

```powershell
python rag_posts.py <commande> [options]
```

Les commandes disponibles : `build`, `ask`, `chat`, `stats`, `memory`.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
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
