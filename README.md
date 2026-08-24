# RSSResume

RSSResume génère un résumé quotidien de vos articles FreshRSS, catégorie par catégorie, produit un fichier audio pour chaque catégorie et peut envoyer le tout par email.

## Fonctionnement

1. connexion à l'API Google Reader compatible de FreshRSS
2. lecture des articles du jour pour chaque catégorie ciblée (les flux hors catégorie sont ignorés)
3. notation de chaque article : score de 0 à 10, thématique et angle, sur titre + extrait court
4. sélection des articles au-dessus du seuil, puis regroupement par thématique pour l'écoute
5. pour les avis de vulnérabilité trop courts, lecture de la page de l'avis pour en avoir le détail
6. résumé texte de la sélection, en prose continue, sans lien ni liste (le texte part en audio),
   chaque sujet attribué au nom de son flux entre parenthèses
7. synthèse audio par catégorie (API OpenAI-compatible si configurée, sinon `espeak` en local)
8. écriture des tags de la catégorie : `score-NN`, `theme-<thematique>`, `scoring-<hash>`,
   `digested` sur les retenus
9. envoi d'un email avec les fichiers audio en pièces jointes et les liens des articles retenus
10. marquage comme lu de tous les articles récupérés

Les étapes 2 à 8 se répètent par catégorie. Les tags sont écrits au fil de l'eau — ce sont des
données de cache, une panne en cours de route ne doit pas faire repayer le scoring déjà effectué.
Le marquage comme lu, lui, n'intervient qu'après l'envoi : un échec d'email laisse les articles non
lus, et le prochain passage les reprend sans repayer le scoring.

Un article déjà noté n'est **pas renoté** : sa note est relue de ses tags FreshRSS. Le scoring n'est
recalculé que si le prompt ou le modèle a changé, ce que détecte un tag d'empreinte. Relancer la
même journée ne coûte donc rien en scoring.

Une catégorie sans article du jour ne déclenche aucun appel IA ni synthèse vocale : seul un fichier
marqueur vide `<categorie>.no-article` est écrit. Même chose quand le scoring ne retient **aucun**
article : pas de résumé ni d'audio, mais le marqueur liste alors les scores obtenus, du meilleur au
moins bon, de quoi juger le seuil d'un coup d'œil.

Le détail de chaque étape, les schémas et les tags posés : **[FONCTIONNEMENT.md](FONCTIONNEMENT.md)**.

## Fichiers produits

Un sous-répertoire par journée, au format `yyyy-MM-dd` :

```
output/
└── 2026-08-23/
    ├── tech.mp3             # catégorie avec articles retenus (.wav sans API OpenAI)
    ├── news.no-article      # catégorie vide, fichier de taille nulle
    └── culture.no-article   # articles lus, aucun retenu : la liste des scores
```

Le marqueur d'une catégorie dont rien n'a passé le seuil ressemble à ceci :

```
Aucun article retenu sur 3 (seuil 7).

 5/10 - Un nouveau format d'archive open source
 4/10 - Bilan trimestriel d'un fournisseur cloud américain
 1/10 - Test d'un casque audio sans fil
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
- `RSSRESUME_PROFILE` — profil de pertinence, en clair (voir ci-dessous)
- `RSSRESUME_PROFILE_FILE=profil.txt` — le même, dans un fichier
- `RSSRESUME_SCORE_THRESHOLD=7` — score minimal pour entrer dans le digest
- `RSSRESUME_MAX_DIGEST_ITEMS=12` — nombre maximum d'articles retenus par catégorie
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_SUMMARY_MODEL=gpt-4o-mini` — résumé audio d'une catégorie
- `OPENAI_SCORING_MODEL=gpt-4o-mini` — notation des articles
- `OPENAI_ARTICLE_MODEL=gpt-4o` — résumé par article (`summarize_top`, hors pipeline)
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `OPENAI_TTS_INSTRUCTIONS` — consignes de diction (ton, débit, émotion), pour les modèles
  qui les acceptent. Non envoyé si vide.
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
python -m rssresume                        # exécution normale du jour
python -m rssresume --date 2026-08-23      # rejouer une journée précise
```

### Options

| Option | Effet |
| --- | --- |
| `--date YYYY-MM-DD` | journée à traiter (défaut : aujourd'hui) |
| `--no-email` | n'envoie pas l'email |
| `--no-tags` | n'écrit aucun tag FreshRSS (`score-NN`, `theme-<thematique>`, `scoring-<hash>`, `digested`) |
| `--no-mark-read` | laisse les articles non lus dans FreshRSS |
| `--dry-run` | raccourci pour les trois options précédentes |

Les trois axes sont indépendants et se cumulent :

| Commande | Email | Tags | Marqué lu |
| --- | :---: | :---: | :---: |
| `python -m rssresume` | oui | oui | oui |
| `--no-email` | non | oui | oui |
| `--no-tags` | oui | non | oui |
| `--no-mark-read` | oui | oui | non |
| `--no-email --no-mark-read` | non | oui | non |
| `--dry-run` | non | non | non |

### Changer de profil de pertinence

Le profil est le **seul** élément personnel du système : c'est lui qui décide ce qui monte
au-dessus du seuil, ce qui est raconté et sous quel angle. Les trois prompts l'utilisent —
notation, résumé d'article, digest audio. Ouvrir l'outil à quelqu'un d'autre, c'est changer ce
texte, et rien d'autre.

```bash
RSSRESUME_PROFILE="Sage-femme libérale. Veille : santé publique, nomenclature, matériel."
# ou, pour un profil long ou versionné à part :
RSSRESUME_PROFILE_FILE=profil.txt
```

Sans l'une ni l'autre, `DEFAULT_PROFIL` de [profil.py](rssresume/profil.py) s'applique. Le profil
est résolu **une fois au démarrage** : un fichier annoncé mais illisible fait échouer le lancement
plutôt que de retomber en silence sur un autre profil. Et comme l'empreinte de scoring inclut le
profil, en changer renote automatiquement les articles concernés : aucun score calculé contre
l'ancien profil ne survit.

### Mettre au point le prompt de scoring

```bash
python -m rssresume --no-email --no-mark-read
```

Les scores sont écrits — donc mis en cache — mais les articles restent non lus et aucun email ne
part. Tant que le profil et le barème ne changent pas, les essais suivants ne repaient pas le
scoring. Modifier l'un des deux change l'empreinte et déclenche la renotation des seuls articles
concernés.

`--dry-run` n'écrit rien, y compris les scores : chaque essai repaie alors le scoring complet.

### Divers

- sans `RSSRESUME_CATEGORIES`, toutes les catégories FreshRSS détectées sont traitées.
- `RSSRESUME_EXCLUDED_CATEGORIES` retire des catégories de la liste traitée (comparaison insensible à la casse).
- tester le scoring seul sur trois articles en dur, sans FreshRSS ni email :
  `python -m rssresume.processing` (nécessite `OPENAI_API_KEY`).

## Organisation du code

Un module par thème technique, dans [rssresume/](rssresume/) :

| Module | Rôle |
| --- | --- |
| `config.py` | configuration lue depuis l'environnement |
| `models.py` | objets métier (`Article`, `CategoryDigest`) |
| `protocols.py` | contrats des collaborateurs de `DigestService` |
| `freshrss.py` | client de l'API Google Reader de FreshRSS (lecture, tags, marquage comme lu) |
| `llm.py` | adaptateur vers une API compatible OpenAI : requêtes, réglages par type d'appel |
| `profil.py` | profil de pertinence : le défaut, et son injection depuis l'extérieur |
| `processing.py` | notation des articles selon le profil de pertinence |
| `cve.py` | lecture de la page d'un avis de vulnérabilité, quand le flux n'en dit rien |
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
[Tech] 24 article(s)
  scoring : 18 score(s) relu(s) des tags, 6 à calculer
  sélection : 5 article(s) retenu(s) sur 24 (seuil 7)
  résumé via l'API gpt-4o-mini (5 article(s))
  synthèse vocale via l'API gpt-4o-mini-tts (voix alloy)
  audio écrit : tech.mp3 (48213 octets)
FreshRSS : notation de 6 article(s) sur 4 valeur(s) de score et 3 thématique(s)
FreshRSS : tag 'digested' sur 5 article(s)
[News] 9 article(s)
  scoring : 0 score(s) relu(s) des tags, 9 à calculer
  sélection : 0 article(s) retenu(s) sur 9 (seuil 7)
  aucun article retenu : news.no-article (ni IA ni synthèse vocale)
FreshRSS : notation de 9 article(s) sur 5 valeur(s) de score et 4 thématique(s)
[Culture] 0 article(s)
  aucun article : culture.no-article (ni IA ni synthèse vocale)
Email : envoi à dest@example.com via smtp.example.com:587 (1 pièce(s) jointe(s))
Email : envoyé
FreshRSS : marquage de 33 article(s) comme lus
Terminé : 33 article(s) lu(s), 5 retenu(s), 1 fichier(s) audio, 1 catégorie(s) sans article, 1 sans article retenu
```

Pour utiliser le paquet comme bibliothèque sans cette sortie : `rssresume.console.enable(False)`.

## Tests

```bash
python -m unittest discover -s tests -t tests
```