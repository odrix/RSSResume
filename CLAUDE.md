# RSSResume

Digest quotidien des articles FreshRSS : notation par LLM, résumé, synthèse vocale, envoi
par email. Ce que fait le produit est écrit dans [README.md](README.md) et le détail de
chaque étape dans [FONCTIONNEMENT.md](FONCTIONNEMENT.md) — les lire, ne pas les redemander.

Ce fichier ne dit que ce que le code ne montre pas.

## Communication

- Répondre en français.
- Le code de ce projet est en français : docstrings, commentaires et noms métier
  (`Lettre`, `ancres`, `pour_envoi`, `no_article_message`). S'y conformer ; ne pas
  angliciser l'existant.
- Une docstring dit **pourquoi** le choix a été fait, pas ce que le code donne déjà à lire.
  C'est le style du dépôt, le tenir.

## Tests

Le projet tourne sur **unittest**, pas pytest — il n'y a ni `pytest.ini`, ni `pyproject.toml`,
ni pytest installé. La commande, depuis la racine :

```
.venv/Scripts/python.exe -m unittest discover -s tests -p "test*.py"
```

Environ 1,5 s pour la suite entière (407 tests au 2026-08-30). Il n'y a donc jamais de
raison de n'en lancer qu'une partie.

- Une tâche n'est pas finie tant que la suite n'est pas verte. Annoncer le nombre de tests.
- Tout comportement ajouté ou corrigé vient avec son test dans `tests/`.

## Outils

- **Modifier les fichiers avec Edit/Write.** Jamais `sed -i`, jamais de heredoc, jamais de
  redirection shell : `core.autocrlf=true` sans `.gitattributes`, un `sed -i` a déjà réécrit
  tout le dépôt en LF, et les heredocs mangent les échappements.
- Lire et chercher avec Read/Grep/Glob. Bash sert à **exécuter** — tests, git, docker — pas
  à éditer ni à inspecter.

## Secrets

Ne jamais lire ni écrire `.env` ni `.env.local` : ce sont les fichiers de l'utilisateur,
gitignorés. Une nouvelle variable se documente dans `.env.example`, commentée dans le style
des autres. Dire ensuite explicitement la ligne à coller dans `.env.local` et ce qui reste
inactif tant que ce n'est pas fait.

## Conception

- **Objet ou fonctionnel.** Une classe de base qui porte les opérations métier, des
  sous-classes qui ne redéfinissent que ce qui diffère, la configuration injectée au
  constructeur : le modèle est [llm/base.py](rssresume/llm/base.py). Pas de dispatch par
  dict de fonctions, pas de dicts ni de tuples passés de module en module — un tel design
  a déjà été rejeté en bloc ici.
- Les données de configuration hors du code ([llm/providers.json](rssresume/llm/providers.json)),
  l'environnement pour les seuls secrets et le choix du fournisseur.
- **Pas de nouvelle dépendance tierce sans demander.** Le projet tourne sur la bibliothèque
  standard, `tzdata` excepté ; l'image Docker n'embarque même pas pip. Pas de SDK OpenAI ni
  Mistral : les appels passent par `urllib` dans `llm/base.py`.
- Rester dans le périmètre demandé : pas de refactor opportuniste, pas de reformatage d'un
  fichier qu'on n'avait pas à toucher.
- **Au-delà de deux fichiers touchés, proposer un plan d'abord** — structure des classes,
  liste exacte des fichiers, dépendances éventuelles — et attendre l'accord avant d'écrire.

## Repères dans le code

- [cli.py](rssresume/cli.py) — les arguments, et `build_service()`, le **seul** endroit où
  les fournisseurs sont choisis et les collaborateurs injectés.
- [digest.py](rssresume/digest.py) — `DigestService` : ce que la journée contient. Pas de
  quoi elle a l'air.
- [newsletter.py](rssresume/newsletter.py) — `Lettre` : la mise en forme de l'email, partagée
  par la production du jour et le renvoi `--send-only`.
- [llm/](rssresume/llm/) — `base.py` le contrat et le transport, `openai.py` / `mistral.py`
  les seuls dialectes, `prompts.py` les prompts, `providers.json` les réglages non secrets.
- [runlog.py](rssresume/runlog.py) — les journaux `<categorie>.log.json` : ils portent tout
  ce que l'email montre, ce qui permet `--send-only` sans aucun appel IA.
- [external/](rssresume/external/) — FreshRSS et les deux transports d'email.
- [protocols.py](rssresume/protocols.py) — les contrats des collaborateurs injectés.

## Exploitation

- Le VPS Dokploy filtre les ports 25, 465 et 587 en sortie : le SMTP y expire en silence.
  `RSSRESUME_MAIL_TRANSPORT=resend` est la réponse, ne pas rediagnostiquer.
- Un digest qui n'arrive pas : vérifier d'abord que le domaine de `SMTP_FROM` résout (NS, A,
  MX, SPF) avant de soupçonner le code. Un domaine NXDOMAIN est refusé par Gmail et
  invérifiable par Resend.
- Relancer une journée ne recoûte pas le scoring : il est relu des tags FreshRSS, et n'est
  recalculé que si le prompt ou le modèle a changé.
