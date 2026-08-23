# RSSResume

RSSResume génère un résumé quotidien de vos articles FreshRSS, catégorie par catégorie, produit un fichier audio pour chaque catégorie et peut envoyer le tout par email.

## Fonctionnement

1. connexion à l'API Google Reader compatible de FreshRSS
2. lecture des articles du jour pour chaque catégorie ciblée
3. génération d'un résumé texte par catégorie
4. synthèse audio par catégorie (`espeak` en local ou API OpenAI-compatible)
5. envoi d'un email avec les fichiers audio en pièces jointes

## Configuration

Variables obligatoires pour FreshRSS :

- `FRESHRSS_BASE_URL`
- `FRESHRSS_USERNAME`
- `FRESHRSS_API_PASSWORD`

Variables optionnelles :

- `RSSRESUME_CATEGORIES=Tech,News`
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

```bash
python -m rssresume --date 2026-08-23 --dry-run
```

- `--dry-run` génère les résumés et les fichiers audio sans envoyer d'email.
- sans `RSSRESUME_CATEGORIES`, toutes les catégories FreshRSS détectées sont traitées.

## Tests

```bash
python -m unittest discover -s tests
```