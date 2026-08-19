# Documentation

Bienvenue dans la documentation du projet **RAG sur export Facebook**.

Ce dossier explique ce que fait le projet, sur quelles technologies il repose et comment il les met en œuvre.

## Sommaire

| Fichier | Contenu |
| --- | --- |
| [projet.md](projet.md) | Présentation du projet : objectif, données, pipeline complet, limites. |
| [technologies.md](technologies.md) | Les technologies utilisées (langage, bibliothèques, services) et comment chacune est employée, avec des extraits de code. |
| [architecture.md](architecture.md) | Structure du code : organisation des fonctions, flux de données, formats des fichiers produits. |
| [usage.md](usage.md) | Guide d'utilisation des six commandes de l'outil en ligne de commande. |

## En bref

Le projet construit un index local à partir d'un export JSON de publications Facebook, puis permet de :

- **chercher** dans ses posts par mots-clés (TF-IDF) ;
- **poser des questions** et obtenir une réponse rédigée via un LLM local (Ollama) ;
- **discuter en continu** avec un chatbot interactif ;
- **analyser** ses publications (activité, types, thèmes, domaines partagés) ;
- **exporter** une « mémoire » en Markdown, classée par thèmes ;
- **générer des articles de blog** structurés à partir des posts, via Ollama, avec sources intégrées.

Tout est fait en local : les données restent sur la machine, seul un LLM local éventuel est utilisé.

## Fichiers du projet

| Fichier | Rôle |
| --- | --- |
| `rag_posts.py` | Script principal, contient tout le code. |
| `your_posts__check_ins__photos_and_videos_1.json` | Export Facebook brut (5 539 publications). |
| `requirements.txt` | Dépendances Python (`scikit-learn`). |
| `rag_index.pkl` | Index TF-IDF sérialisé, produit par la commande `build` (généré, ignoré par git). |
| `memory.md` | Mémoire Markdown générée par la commande `memory` (généré, ignoré par git). |
| `blog_posts/` | Dossier contenant les articles de blog générés par la commande `blog` (généré, ignoré par git). |
