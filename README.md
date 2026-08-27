# RSSResume

RSSResume génère un résumé quotidien de vos articles FreshRSS, catégorie par catégorie, produit un fichier audio pour chaque catégorie et peut envoyer le tout par email.

## Fonctionnement

1. connexion à l'API Google Reader compatible de FreshRSS
2. lecture des articles du jour pour chaque catégorie ciblée (les flux hors catégorie sont ignorés)
3. notation de chaque article : score de 0 à 10, thématique et angle, sur titre + extrait court
4. sélection des articles au-dessus du seuil — celui de la catégorie, abaissé les jours
   creux — puis regroupement par thématique pour l'écoute
5. pour les avis de vulnérabilité trop courts, lecture de la page de l'avis pour en avoir le détail
6. résumé texte de la sélection, en prose continue, sans lien ni liste (le texte part en audio),
   ouvert et fermé par une phrase courte qui juge la journée, et sans jamais nommer le média
7. synthèse audio par catégorie (fournisseur configuré — OpenAI ou Mistral —, sinon `espeak` en local)
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
    ├── tech.mp3             # catégorie avec articles retenus (.wav sans fournisseur)
    ├── tech.log.json        # journal de la catégorie : articles, scores, coûts
    ├── culture.no-article   # articles lus, aucun retenu : la liste des scores
    ├── culture.log.json     # les scores obtenus et le scoring déjà payé
    └── news.no-article      # catégorie vide : pas de journal, il ne dirait que des zéros
```

Toute catégorie qui a lu au moins un article a son **journal** `<categorie>.log.json` — y
compris sans sélection, et même après une erreur en cours de route.

Le marqueur d'une catégorie dont rien n'a passé le seuil ressemble à ceci :

```
Aucun article retenu sur 3 (seuil 7).

 5/10 - Un nouveau format d'archive open source
 4/10 - Bilan trimestriel d'un fournisseur cloud américain
 1/10 - Test d'un casque audio sans fil
```

Seuls les fichiers audio sont joints à l'email.

### Le journal d'une catégorie

`<categorie>.log.json` fixe ce qu'une exécution finie ne conservait nulle part :

| Bloc | Contenu |
| --- | --- |
| `articles` | tous les articles lus, les mieux notés en tête : score, thématique, angle, retenu ou non, et si la note a été calculée ou relue des tags |
| `couts` | le coût des appels IA, détaillé **par typologie** — somme des scorings, somme des résumés, somme de la synthèse vocale — puis appel par appel |
| `parametres`, `resultat` | seuil de la catégorie, seuil de repli, plafond, modèles, empreinte de scoring ; statut, compteurs, **seuil réellement appliqué** ce jour-là, fichier produit |

```json
{
  "categorie": "Tech",
  "date": "2026-08-23",
  "parametres": { "seuil": 7, "seuil_repli": 5, "plafond": 12, "…": "…" },
  "resultat": { "statut": "audio", "articles": 24, "retenus": 5, "seuil_applique": 7, "…": "…" },
  "couts": {
    "devise": "USD",
    "total": 0.014327,
    "tarification_complete": true,
    "modeles_sans_tarif": [],
    "par_typologie": {
      "scoring": { "appels": 1, "tokens_entree": 4820, "tokens_sortie": 611, "cout": 0.001089 },
      "resume":  { "appels": 1, "tokens_entree": 39104, "tokens_sortie": 812, "cout": 0.013118 },
      "tts":     { "appels": 1, "caracteres": 3187, "cout": 0.000120 }
    },
    "appels": [ "… le détail de chaque appel …" ]
  },
  "articles": [ "… un objet par article lu …" ]
}
```

**Un appel par poste, ce n'est pas une remontée partielle.** Le scoring part par lots de 40
articles : une catégorie de 19 articles tient en un appel. Le résumé et la synthèse vocale, eux,
sont produits en un seul appel pour toute la catégorie, quel qu'en soit le nombre d'articles
retenus. `appels` monte donc à 2 pour le scoring à partir du 41ᵉ article, et reste à 1 partout
ailleurs.

Les prix viennent d'une grille statique ([llm/providers.json](rssresume/llm/providers.json), bloc `prices`
de chaque fournisseur), **à revérifier** :
un tarif périmé s'y lit comme un coût réel. Un modèle absent de la grille n'est pas facturé à zéro :
son coût passe à `null`, son nom est listé dans `modeles_sans_tarif`, `tarification_complete` passe
à `false`, et le total de son poste comme le total général passent à `null` eux aussi — une somme
partielle se lit exactement comme une somme complète. Un nom daté (`gpt-4o-mini-2024-07-18`) retombe
sur sa famille, mais un simple préfixe commun ne suffit pas : `gpt-5.6-luna` n'est pas `gpt-5`, et
n'est donc pas tarifé par défaut.
`RSSRESUME_PRICES` complète ou corrige la grille sans toucher au code :

```bash
RSSRESUME_PRICES='{"gpt-5.6-luna": {"input": 1.25, "output": 10.00}}'
```

La synthèse vocale ne renvoie aucun compteur de tokens : son coût est exact quand le modèle est
facturé au caractère (`tts-1`), estimé à partir du texte envoyé sinon (`gpt-4o-mini-tts`), et
l'appel porte alors `"cout_estime": true`.

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
- `RSSRESUME_CATEGORY_THRESHOLDS=Tech generaliste=5` — seuil propre à une catégorie, sous
  la forme `Catégorie=score`, plusieurs entrées séparées par des virgules
- `RSSRESUME_MIN_DIGEST_ITEMS=5` — en dessous de ce nombre de retenus, le seuil de la
  catégorie tombe à `RSSRESUME_FALLBACK_THRESHOLD` pour la journée ; `0` désactive le repli
- `RSSRESUME_FALLBACK_THRESHOLD=5` — le seuil de repli
- `RSSRESUME_MAX_DIGEST_ITEMS=12` — nombre maximum d'articles retenus par catégorie
- `RSSRESUME_PRICES` — grille de tarifs JSON, pour les modèles absents de `providers.json`

### Fournisseurs de LLM

Deux fournisseurs sont livrés, **OpenAI** et **Mistral**. Dans l'environnement, seulement
deux choses : les clés d'API, et qui fait quoi.

```bash
OPENAI_API_KEY=sk-…
MISTRAL_API_KEY=…

RSSRESUME_PROVIDER=openai        # vaut pour toutes les actions (défaut : openai)
RSSRESUME_TTS_PROVIDER=mistral   # sauf celle-ci
```

Les actions sont `SCORING` (notation), `ARTICLE` (résumé d'un article), `DIGEST` (résumé
de catégorie) et `TTS` (synthèse vocale) ; chacune accepte un
`RSSRESUME_<ACTION>_PROVIDER`. Chaque fournisseur n'utilise que **sa** clé : sans
`MISTRAL_API_KEY`, une action confiée à Mistral retombe sur le local — résumé extractif,
ou `espeak` pour la voix — plutôt que d'emprunter celle d'OpenAI.

Tout le reste — endpoint, modèle et réglages par action, voix, format audio, tarifs —
n'est pas secret et vit dans [llm/providers.json](rssresume/llm/providers.json) :

```json
"mistral": {
  "base_url": "https://api.mistral.ai/v1",
  "actions": {
    "scoring": {"model": "mistral-small-latest", "temperature": 0.1, "max_tokens": 4096},
    "digest":  {"model": "mistral-medium-latest", "temperature": 0.4}
  },
  "tts": {"model": "voxtral-mini-tts-2603", "voice": "fr_marie_curious", "format": "mp3"},
  "prices": {"voxtral-mini-tts-2603": {"characters": 16.00}}
}
```

- `RSSRESUME_PROVIDERS_FILE=providers.json` — un fichier fusionné par-dessus, clé à clé :
  on n'y redéclare que ce que l'on change.

Les consignes de diction d'OpenAI (`instructions` du bloc `tts`) y ont leur place : le
rythme se joue là autant que dans le texte du résumé. Mistral n'en a pas — son
`/v1/audio/speech` n'a pas de champ pour elles, tout se joue dans le choix de la voix.

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
| `--include-read` | redemande aussi les articles déjà lus, que l'API exclut par défaut |
| `--dry-run` | raccourci pour `--no-email --no-tags --no-mark-read` |

Les trois axes sont indépendants et se cumulent :

| Commande | Email | Tags | Marqué lu |
| --- | :---: | :---: | :---: |
| `python -m rssresume` | oui | oui | oui |
| `--no-email` | non | oui | oui |
| `--no-tags` | oui | non | oui |
| `--no-mark-read` | oui | oui | non |
| `--no-email --no-mark-read` | non | oui | non |
| `--dry-run` | non | non | non |

`--include-read` est d'un autre ordre : il ne décide pas de ce qu'on écrit, mais de ce qu'on
demande. Les articles du jour sont récupérés **non lus uniquement** — l'API les filtre, ce qui
évite de paginer tout le flux —, donc rejouer une journée déjà livrée exige de les redemander :

```bash
python -m rssresume --date 2026-08-23 --include-read --no-email
```

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
  `python -m rssresume.llm.processing` (nécessite la clé du fournisseur actif, `OPENAI_API_KEY` par défaut).

## Organisation du code

Un module par thème technique, dans [rssresume/](rssresume/) :

| Module | Rôle |
| --- | --- |
| `cli.py` | arguments, assemblage des composants, `main()` |
| `config.py` | configuration lue depuis l'environnement |
| `models.py` | objets métier (`Article`, `CategoryDigest`) |
| `protocols.py` | contrats des collaborateurs de `DigestService` |
| `profil.py` | profil de pertinence : le défaut, et son injection depuis l'extérieur |
| `digest.py` | orchestration du digest quotidien |
| `summaries.py` | résumé d'une catégorie : celui du fournisseur, ou le repli extractif |
| `audio.py` | synthèse vocale (fournisseur configuré, ou `espeak`) |
| `pricing.py` | lecture de la grille de tarifs et calcul du coût d'un appel |
| `runlog.py` | journal `<categorie>.log.json` : articles, scores et coûts par catégorie |
| **`external/`** | **les systèmes que l'on ne contrôle pas** |
| `external/freshrss.py` | client de l'API Google Reader de FreshRSS (lecture, tags, marquage comme lu) |
| `external/mailer.py` | construction et envoi de l'email |
| **`llm/`** | **tout ce qui parle à un modèle** |
| `llm/providers.json` | réglages non secrets de chaque fournisseur : endpoint, modèles, voix, tarifs |
| `llm/providers.py` | lecture de ces réglages, et choix du fournisseur par action |
| `llm/prompts.py` | les prompts, indépendants de tout fournisseur |
| `llm/base.py` | `LLMProvider` : les quatre opérations, le transport, et la fabrique |
| `llm/openai.py` | `OpenAIProvider` : ce que le dialecte OpenAI change |
| `llm/mistral.py` | `MistralProvider` : idem, dont la synthèse `voice_id` / base64 |
| `llm/processing.py` | relecture des réponses du noteur, et démonstration autonome |
| **`tools/`** | **ce qui ne parle ni de veille, ni de FreshRSS, ni de modèles** |
| `tools/console.py` | suivi d'exécution affiché dans la console |
| `tools/text.py` | nettoyage de HTML, slugs, et quelques phrases toutes faites |
| `tools/cve.py` | lecture de la page d'un avis de vulnérabilité, quand le flux n'en dit rien |

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
  synthèse vocale via openai — gpt-4o-mini-tts (voix alloy)
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