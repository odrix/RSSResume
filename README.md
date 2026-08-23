# RSSResume

RSSResume génère un résumé quotidien de vos articles FreshRSS, catégorie par catégorie, produit un fichier audio pour chaque catégorie et peut envoyer le tout par email.

## Fonctionnement

1. connexion à l'API Google Reader compatible de FreshRSS
2. lecture des articles du jour pour chaque catégorie ciblée (les flux hors catégorie sont ignorés)
3. génération d'un résumé texte par catégorie
4. synthèse audio par catégorie (API OpenAI-compatible si configurée, sinon `espeak` en local)
5. envoi d'un email avec les fichiers audio en pièces jointes
6. marquage des articles traités comme lus dans FreshRSS (`edit-tag`)

Le marquage n'intervient qu'après l'envoi de l'email : un échec d'envoi laisse les articles non lus,
et le prochain passage les reprend.

Une catégorie sans article du jour ne déclenche aucun appel IA ni synthèse vocale : seul un fichier
marqueur vide `<categorie>.no-article` est écrit.

## Fichiers produits

Un sous-répertoire par journée, au format `yyyy-MM-dd` :

```
output/
└── 2026-08-23/
    ├── tech.mp3          # catégorie avec articles (.wav sans API OpenAI)
    └── news.no-article   # catégorie vide, fichier de taille nulle
```

Seuls les fichiers audio sont joints à l'email.

## Configuration

Variables obligatoires pour FreshRSS :

- `FRESHRSS_BASE_URL`
- `FRESHRSS_USERNAME`
- `FRESHRSS_API_PASSWORD`

Variables optionnelles :

- `RSSRESUME_CATEGORIES=Tech,News`
- `RSSRESUME_EXCLUDED_CATEGORIES=Non classé`
- `RSSRESUME_OUTPUT_DIR=output`
- `RSSRESUME_SUMMARY_LANGUAGE=fr`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_SUMMARY_MODEL`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_TO=dest@example.com`
- `SMTP_USE_TLS=true`
- `SMTP_USE_SSL=false`

## Exécution

set env variables
```bash
Get-Content .env.local | ? {$_ -match '^\s*[^#]'} | % { $kv = $_ -split '=',2; Set-Item "env:$($kv[0].Trim())" $kv[1].Trim() }
```

```bash
python -m rssresume --date 2026-08-23 --dry-run
```

- `--dry-run` génère les résumés et les fichiers audio sans envoyer d'email ni marquer les articles comme lus.
- sans `RSSRESUME_CATEGORIES`, toutes les catégories FreshRSS détectées sont traitées.
- `RSSRESUME_EXCLUDED_CATEGORIES` retire des catégories de la liste traitée (comparaison insensible à la casse).

## Organisation du code

Un module par thème technique, dans [rssresume/](rssresume/) :

| Module | Rôle |
| --- | --- |
| `config.py` | configuration lue depuis l'environnement |
| `models.py` | objets métier (`Article`, `CategoryDigest`) |
| `protocols.py` | contrats des collaborateurs de `DigestService` |
| `freshrss.py` | client de l'API Google Reader de FreshRSS (lecture et marquage comme lu) |
| `llm.py` | transport HTTP vers une API compatible OpenAI |
| `summaries.py` | génération des résumés textuels |
| `audio.py` | synthèse vocale (OpenAI ou `espeak`) |
| `mailer.py` | construction et envoi de l'email |
| `digest.py` | orchestration du digest quotidien |
| `cli.py` | arguments, assemblage des composants, `main()` |
| `console.py` | suivi d'exécution affiché dans la console |

Les tests suivent le même découpage (`tests/test_<module>.py`, doublures partagées dans `tests/support.py`).

## Suivi d'exécution

L'exécution est tracée sur la sortie standard :

```
RSSResume : digest du 2026-08-23 vers output/2026-08-23
FreshRSS : authentifié en tant que mon-utilisateur
FreshRSS : 3 catégorie(s) découverte(s)
3 catégorie(s) à traiter : Tech, News, Culture
[Tech] 3 article(s)
  résumé via l'API gpt-4o-mini (3 article(s))
  synthèse vocale via l'API gpt-4o-mini-tts (voix alloy)
  audio écrit : tech.mp3 (48213 octets)
[Culture] 0 article(s)
  aucun article : culture.no-article (ni IA ni synthèse vocale)
Email : envoi à dest@example.com via smtp.example.com:587 (2 pièce(s) jointe(s))
Email : envoyé
FreshRSS : marquage de 4 article(s) comme lus
Terminé : 4 article(s), 2 fichier(s) audio, 1 catégorie(s) sans article
```

Pour utiliser le paquet comme bibliothèque sans cette sortie : `rssresume.console.enable(False)`.

## Tests

```bash
python -m unittest discover -s tests
```