# RSSResume

RSSResume génère un résumé quotidien de vos articles FreshRSS, catégorie par catégorie, en produit
la version audio et peut envoyer le tout par email.

Deux façons d'écouter, au choix (`RSSRESUME_AUDIO_MODE`) : **un fichier par catégorie**, ou **un
seul fichier pour toute la journée** — salutation, éphéméride, les catégories enchaînées et une
conclusion sur ce qui reste à faire. Voir [Les deux modes audio](#les-deux-modes-audio).

## Fonctionnement

1. connexion à l'API Google Reader compatible de FreshRSS
2. lecture des articles du jour pour chaque catégorie ciblée (les flux hors catégorie sont ignorés)
3. notation de chaque article : score de 0 à 10, thématique et angle, sur titre + extrait court
4. sélection des articles au-dessus du seuil — celui de la catégorie, abaissé les jours
   creux — puis regroupement par thématique pour l'écoute
5. pour les avis de vulnérabilité trop courts, lecture de la page de l'avis pour en avoir le détail
6. résumé texte de la sélection, en prose continue, sans lien ni liste (le texte part en audio),
   ouvert et fermé par une phrase courte qui juge la journée, et sans jamais nommer le média
7. synthèse audio (fournisseur configuré — OpenAI ou Mistral —, sinon `espeak` en local) : par
   catégorie, ou en un seul fichier une fois toutes les catégories traitées
8. écriture des tags de la catégorie, préfixés par le profil : `<username>-score-NN`,
   `<username>-theme-<thematique>`, `<username>-scoring-<hash>`, `<username>-digested` sur les retenus
9. envoi d'un email avec les fichiers audio en pièces jointes et les liens des articles retenus
10. marquage comme lu de tous les articles récupérés, une fois **tous** les profils servis

Les étapes 2 à 9 se répètent pour chaque profil (voir [Plusieurs profils](#plusieurs-profils)),
et les étapes 2 à 8 par catégorie. Les tags sont écrits au fil de l'eau — ce sont des
données de cache, une panne en cours de route ne doit pas faire repayer le scoring déjà effectué.
Le marquage comme lu, lui, n'intervient qu'après l'envoi de tous les profils : un échec laisse les
articles non lus, et le prochain passage les reprend sans repayer le scoring.

Un article déjà noté n'est **pas renoté** : sa note est relue de ses tags FreshRSS. Le scoring n'est
recalculé que si le prompt ou le modèle a changé, ce que détecte un tag d'empreinte. Relancer la
même journée ne coûte donc rien en scoring.

Une catégorie sans article du jour ne déclenche aucun appel IA ni synthèse vocale : seul un fichier
marqueur vide `<categorie>.no-article` est écrit. Même chose quand le scoring ne retient **aucun**
article : pas de résumé ni d'audio, mais le marqueur liste alors les scores obtenus, du meilleur au
moins bon, de quoi juger le seuil d'un coup d'œil.

Une catégorie peut aussi être **routée hors de ce pipeline** : voir
[Les avis CERT-FR, sans IA](#les-avis-cert-fr-sans-ia).

Le détail de chaque étape, les schémas et les tags posés : **[FONCTIONNEMENT.md](FONCTIONNEMENT.md)**.

## Fichiers produits

Un sous-répertoire par profil, nommé par son identifiant (`id`, un UUID), puis par journée au
format `yyyy-MM-dd` :

```
output/
└── 5f0c2d8e-7a1b-4c3d-9e8f-0a1b2c3d4e5f/   # l'id du profil, pas son nom
    └── 2026-08-23/
        ├── tech.mp3             # catégorie avec articles retenus (.wav sans fournisseur)
        ├── tech.log.json        # journal de la catégorie : articles, scores, coûts
        ├── culture.no-article   # articles lus, aucun retenu : la liste des scores
        ├── culture.log.json     # les scores obtenus et le scoring déjà payé
        ├── news.no-article      # catégorie vide : pas de journal, il ne dirait que des zéros
        └── journee.json         # l'éphéméride du jour, et le montage s'il y en a eu un
```

L'identifiant plutôt que le nom : renommer quelqu'un ne le sépare pas de ses journées. Il est lu
à la clé `id` du document ; absent, il est généré et écrit dans le fichier au premier passage.

Les journées produites avant les profils sont directement sous `output/<date>/`. Pour que
`--send-only` et `--journal` les retrouvent, les déplacer une fois sous l'identifiant du profil
(ici `adrien` ; la première commande génère l'id s'il manque, et l'affiche) :

```bash
ID=$(python -c "from rssresume.profil import charger_profil; print(charger_profil('input/profils', 'adrien').id)")
cd output && mkdir -p "$ID" && mv [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] "$ID"/
```

Dans le conteneur, voir [todo-dockploy.md](todo-dockploy.md).

En mode `global`, les `<categorie>.mp3` laissent la place à un seul `journee.mp3`, dont le texte
est conservé dans `journee.json`. Tout le reste est identique.

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
- `RSSRESUME_TIMEZONE=Europe/Paris` — fuseau dans lequel une journée commence et finit.
  En UTC, un article publié à 1 h du matin à Paris en heure d'été tombe dans la veille,
  donc dans une journée déjà livrée : il n'apparaît dans aucun digest
- `RSSRESUME_PROFILES_DIR=/data/profils` — le dossier des profils, un `{username}.json` par
  personne (voir [Plusieurs profils](#plusieurs-profils)). Exclusif des deux suivantes
- `RSSRESUME_PROFILE_FILE=input/moi/adrien.json` — le document d'une seule personne : profil de
  pertinence, stack surveillée, destinataire du digest (voir ci-dessous). Le nom du fichier
  devient le nom du profil
- sans l'une ni l'autre, aucun profil : le passage ne fait rien. `RSSRESUME_PROFILE` (le profil
  en clair) n'est plus lue, et fait échouer le lancement si elle est posée
- `RSSRESUME_SCORE_THRESHOLD=7` — score minimal pour entrer dans le digest
- `RSSRESUME_CATEGORY_THRESHOLDS=Tech generaliste=5` — seuil propre à une catégorie, sous
  la forme `Catégorie=score`, plusieurs entrées séparées par des virgules
- `RSSRESUME_MIN_DIGEST_ITEMS=5` — en dessous de ce nombre de retenus, le seuil de la
  catégorie tombe à `RSSRESUME_FALLBACK_THRESHOLD` pour la journée ; `0` désactive le repli
- `RSSRESUME_FALLBACK_THRESHOLD=5` — le seuil de repli
- `RSSRESUME_MAX_DIGEST_ITEMS=12` — nombre maximum d'articles retenus par catégorie
- `RSSRESUME_ARTICLE_CHAR_LIMIT=8000` — plafond de caractères envoyés au résumeur par
  article, coupé à la dernière phrase entière ; `0` le désactive. À ne pas descendre sous
  6000 : c'est ce que `tools/cve.py` lit sur la page d'un avis, versions touchées comprises
- `RSSRESUME_PRICES` — grille de tarifs JSON, pour les modèles absents de `providers.json`
- `RSSRESUME_CERTFR_CATEGORIES=1 - Alertes et avis CERT-FR ANSSI` — catégories routées
  vers le traitement déterministe, sans aucun appel IA (voir ci-dessous)
- `RSSRESUME_AUDIO_MODE=category` — `category` (défaut) rend un fichier audio par
  catégorie, `global` un seul pour toute la journée (voir ci-dessous). Une valeur
  inconnue fait échouer le lancement
- `RSSRESUME_DEBUG=true` — imprime le bilan de la journée en fin de passage, articles
  compris, sur la sortie standard (voir [Suivre une journée dans le conteneur](#suivre-une-journée-dans-le-conteneur))

### Les deux modes audio

```bash
RSSRESUME_AUDIO_MODE=global
```

En `category` — le défaut, et le comportement historique — chaque catégorie qui a des
articles retenus produit son `<slug>.mp3`, et l'email les joint tous.

En `global`, aucune catégorie ne produit de fichier. Une fois toutes les catégories
traitées, les articles retenus de la journée — **toutes catégories confondues** — sont
remis dans un seul ordre et racontés d'une traite :

- une salutation, qui vous nomme si la clé `prenom` du document de profil est remplie ;
- l'éphéméride du jour, la même que celle qui ouvre l'email, dite à voix haute ;
- une phrase qui annonce ce qui vient, de quoi décider d'écouter jusqu'au bout ;
- les sujets par score décroissant, ceux qui se répondent côte à côte, sans qu'aucune
  catégorie soit nommée, avec une transition de quelques mots entre eux ;
- la phrase des catégories déterministes (avis CERT-FR), relayée telle quelle ;
- une conclusion sur les deux à quatre points actionnables de la journée.

L'ordre est calculé, pas demandé au modèle : le score du scoring d'abord, puis un
regroupement par thématique, à l'échelle de la journée et non d'une catégorie. C'est ce
qui évite qu'un sujet grave passe en huitième position parce que son dossier FreshRSS
est le dernier, et ce qui rapproche deux dépêches du même fait venues de deux catégories.

L'email, lui, ne change pas — il continue de montrer les résumés de chaque catégorie mot
pour mot, avec leurs liens et leur liste « à surveiller ». Seule la pièce jointe est
différente : un `journee.mp3` unique, nommé une fois sous l'introduction.

C'est un appel de complétion de plus par journée, et autant de caractères de synthèse
qu'avant répartis sur moins d'appels : le coût est sensiblement le même. Il apparaît
sous son propre poste, `montage`, dans `journee.json`.

Sans clé d'API pour ce fournisseur, ou si l'appel échoue, les résumés partent bout à
bout sans transitions ni conclusion : l'audio du jour sort quand même, et
`journee.json` le dit (`"origine": "assemblage"` au lieu de `"montage"`).

Pour comparer les deux sur une même journée, `--audio-mode` l'emporte sur la variable
sans qu'il y ait à toucher à l'environnement — et le scoring n'est pas repayé :

```bash
python -m rssresume --date 2026-08-30 --include-read --no-mark-read --no-email --audio-mode global
```

### Les avis CERT-FR, sans IA

Le flux des avis de l'ANSSI ne ressemble à aucune autre catégorie : cinq à dix articles par
jour, tous bâtis sur le même moule — « Multiples vulnérabilités dans *X* (JJ mois AAAA) » et
une phrase de description. Le pipeline LLM y était à contre-emploi : cher, répétitif, et sept
paragraphes qui commencent tous pareil sont exactement ce qu'on n'écoute pas. La seule réponse
utile tient en une ligne : est-ce que ça touche ma stack.

```bash
RSSRESUME_CERTFR_CATEGORIES=1 - Alertes et avis CERT-FR ANSSI
```

La catégorie saute alors le scoring, le résumé et la synthèse vocale, et rend une phrase :

```
7 avis CERT-FR aujourd'hui, 2 touchent la stack :
  Keycloak — exécution de code arbitraire à distance ; OpenSSL — déni de service à distance.
```

Les avis appariés remontent dans la liste « À lire » de l'email, les plus graves en tête ;
**tous** les avis sont marqués lus, appariés ou non. Le journal de la catégorie est écrit
comme les autres, avec `couts.total` à `0.0` — c'est le signal recherché — et `--send-only`
le relit sans traitement particulier.

Le routage est **explicite** : aucune catégorie n'y tombe parce qu'elle s'appelle CERT-FR. Le
libellé est comparé sans tenir compte de la casse **ni des accents** — le libellé réel en
porte, une variable d'environnement les perd volontiers en route, et une catégorie qu'on croit
routée et qui ne l'est pas repasse par le LLM tous les matins sans que rien ne le dise.

**La liste des composants est à remplir**, à la clé `stack` du document de profil : rien n'est
livré, un exemple qui apparierait un vrai avis serait un faux positif offert le jour de
l'installation. Une entrée par composant — une **chaîne** pour le cas courant, un **objet**
quand les avis emploient plusieurs écritures, `nom` étant celui qui sera écrit dans la phrase :

```json
"stack": [
  "Traefik",
  {"nom": "Keycloak", "alias": ["Red Hat Single Sign-On", "RH-SSO"]},
  {"nom": "noyau Linux", "alias": ["Linux kernel"]}
]
```

L'appariement porte sur des **mots entiers**, casse et accents ignorés : « Go » ne reconnaît
pas « Google », et un alias de plusieurs mots exige les mots à la suite — « Apache Tomcat » ne
se reconnaît pas dans un avis qui cite Apache d'un côté et Tomcat de l'autre. Éviter les alias
d'un seul mot courant (« Cloud », « Vault », « Core ») : ils ramènent des faux positifs, et un
composant qui ressort tous les jours finit par rendre la phrase entière inutile.

La criticité est lue dans l'avis lui-même. Un avis CERT-FR ne porte ni score CVSS ni cotation
de gravité : il nomme ce que la faille permet, dans un vocabulaire fixe — « exécution de code
arbitraire à distance », « élévation de privilèges », « déni de service ». C'est ce vocabulaire
qui est reconnu, et le plus grave des impacts annoncés qui est retenu ; quand rien n'est
reconnu, la phrase le dit (« impact non précisé par l'avis ») plutôt que de laisser croire à
une faille bénigne. Rien n'est déduit, rien n'est inventé — sur un avis de sécurité, une
information fabriquée est pire que pas d'information.

La liste n'a pas de variable d'environnement à elle : ce qu'on exploite est aussi personnel que
ce qu'on veut lire, et se déclare au même endroit — le document que `RSSRESUME_PROFILE_FILE`
désigne, hors du dépôt. Elle est lue au lancement, avec le profil : une entrée fautive fait
échouer le démarrage plutôt que la catégorie d'avis d'un matin.

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
de catégorie), `EPHEMERIDE` (le fait du jour), `MONTAGE` (l'audio de journée, en mode
`global` seulement) et `TTS` (synthèse vocale) ; chacune accepte un
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

Le même bloc porte `input_limit`, le plafond d'entrée de l'endpoint de synthèse en
caractères (4000 chez OpenAI, dont l'API refuse au-delà de 4096 — le texte n'est pas
tronqué, l'appel échoue). Au-delà, le texte est découpé entre deux paragraphes, sinon
entre deux phrases, et les audios sont raboutés en un seul fichier. La clé absente —
c'est le cas de Mistral, qui n'annonce pas le sien — envoie le texte d'un seul tenant.

### Envoi de l'email

Le digest part par SMTP, ou par l'API HTTPS de Resend. Deux implémentations du même
contrat, que `RSSRESUME_MAIL_TRANSPORT` départage :

- `RSSRESUME_MAIL_TRANSPORT=smtp` (défaut) — le chemin naturel ;
- `RSSRESUME_MAIL_TRANSPORT=resend` — quand l'hébergeur filtre les ports SMTP en sortie.

Beaucoup d'hébergeurs de VPS ferment 25, 465 et 587 en sortie pour ne pas héberger de
spam. La panne est muette : la connexion expire sur un `TimeoutError(110)` sans que rien
ne soit mal réglé, et l'envoi se distingue mal d'un problème d'identifiants. Un test
depuis le conteneur tranche en dix secondes, et la trace dit tout :

```bash
python -c "import socket; socket.create_connection(('smtp.example.com',587),10)"
```

Un échec sur `sock.connect()` — donc après la résolution DNS — sur les trois ports, c'est
un filtrage réseau. Le 443 sort forcément, lui : c'est déjà par là que passent FreshRSS
et les fournisseurs de LLM. D'où `resend`, qui emprunte le même chemin qu'eux.

`SMTP_FROM` vaut pour les deux transports : l'expéditeur ne change pas de nature parce que
le chemin change. Le reste ne sert qu'au transport `smtp`. Le **destinataire**, lui, n'est
plus une variable : il se déclare à la clé `email` du document de profil. `SMTP_TO` n'est
plus lue et **fait échouer le lancement** tant qu'elle traîne dans l'environnement —
ignorée, elle laisserait croire à un destinataire configuré et le digest ne partirait plus
sans que rien ne le dise.

- `SMTP_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS=true`
- `SMTP_USE_SSL=false`
- `RESEND_API_KEY` — requise par le transport `resend` seulement.

Resend n'accepte d'expéditeur que sur un domaine vérifié chez lui, vérification qui passe
par des enregistrements DNS : un domaine qui ne résout pas ne peut pas l'être. Le compte
de test `onboarding@resend.dev` fait exception, mais n'écrit qu'au propriétaire du compte.

## Dépendances

RSSResume tourne sur la bibliothèque standard, à une exception près :

```bash
pip install -r requirements.txt   # tzdata
```

`tzdata` est la base de fuseaux horaires que lit `zoneinfo`. Linux la fournit, Windows non,
et le découpage des journées en heure locale (`RSSRESUME_TIMEZONE`) en dépend : sans elle,
la configuration échoue au lancement avec un message qui le dit.

## Exécution

set env variables
```bash
Get-Content .env.local | ? {$_ -match '^\s*[^#]'} | % { $kv = $_ -split '=',2; Set-Item "env:$($kv[0].Trim())" $kv[1].Trim() }
```

```bash
python -m rssresume                        # exécution normale du jour, dans RSSRESUME_TIMEZONE
python -m rssresume --date 2026-08-23      # rejouer une journée précise
```

### Options

| Option | Effet |
| --- | --- |
| `--date YYYY-MM-DD` | journée à traiter (défaut : aujourd'hui) |
| `--profil USERNAME` | ne sert que ce profil (défaut : tous) ; vaut aussi pour `--send-only` et `--journal` |
| `--no-email` | n'envoie pas l'email |
| `--no-tags` | n'écrit aucun tag FreshRSS (`<username>-score-NN`, `-theme-<thematique>`, `-scoring-<hash>`, `-digested`) |
| `--no-mark-read` | laisse les articles non lus dans FreshRSS |
| `--include-read` | redemande aussi les articles déjà lus, que l'API exclut par défaut |
| `--send-only` | renvoie l'email d'une journée déjà produite, sans rien recalculer |
| `--journal` | imprime ce qu'une journée déjà produite dit d'elle-même ; ne lit que le disque |
| `--audio-mode category\|global` | un audio par catégorie, ou un seul pour la journée ; l'emporte sur `RSSRESUME_AUDIO_MODE` |
| `--debug` | ajoute le détail des articles au journal, et l'imprime en fin de passage ; l'emporte sur `RSSRESUME_DEBUG` |
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

### Plusieurs profils

Plusieurs personnes peuvent lire le même FreshRSS, chacune avec son profil de pertinence, sa
stack et son adresse. `RSSRESUME_PROFILES_DIR` désigne un dossier qui contient un
`{username}.json` par personne, au format du document de profil (clé `profil` exigée,
`stack`, `email`, `prenom`). Le nom du fichier est le nom du profil : 2 à 32 caractères,
minuscules, chiffres, `-` ou `_`, commençant par une lettre ou un chiffre. Un `.json` au nom
invalide est signalé dans les logs et sauté, les autres profils sont servis ; un dossier absent
fait échouer le lancement ; les fichiers qui ne sont pas des `.json` sont ignorés.

Chaque passage digère la journée pour chaque profil, dans l'ordre alphabétique :

- la sortie va dans `output/<id>/<date>/`, l'email à l'adresse du profil. L'`id` est un UUID
  lu dans le document ; absent, il est généré et **écrit dans le fichier** (JSON indenté, clés
  conservées). Un document en texte brut ne peut pas le porter : ce profil est sauté, avec un
  message qui demande de le convertir en JSON. Deux documents au même `id` sont sautés tous les
  deux, pour ne pas mélanger leurs journées ;
- les tags FreshRSS sont **préfixés** par le nom (`adrien-score-07`) : deux personnes ne
  notent pas un article pareil. Les anciens tags sans préfixe sont ignorés — passer aux
  profils coûte donc **un re-scoring unique** des articles relus ;
- un profil qui échoue (document fautif, fournisseur en panne) est journalisé, et les
  suivants sont servis ;
- les catégories et les articles ne sont lus qu'une fois pour tous les profils, et le
  marquage comme lu n'intervient qu'**une fois tous les profils servis** — sans quoi le
  premier viderait la journée des suivants. Si l'un d'eux a échoué, rien n'est marqué : il
  peut rejouer sa journée avec `--profil` sans `--include-read`. Un passage `--profil` ne
  marque rien non plus tant que d'autres profils existent ; les articles restés non lus ne
  reviennent dans aucune autre journée.

Sans dossier, `RSSRESUME_PROFILE_FILE` reste lu : ce document est l'unique profil, nommé
d'après son fichier (`input/adrien.json` → `adrien`). Sans l'un ni l'autre, aucun profil : le
passage ne lit rien et ne résume rien. Le dossier et `RSSRESUME_PROFILE_FILE` posés ensemble
font échouer le lancement : déplacer le document dans le dossier et retirer la variable.
`RSSRESUME_PROFILE` fait échouer le lancement dans tous les cas.

Avec `RSSRESUME_PROFILES_DB`, les profils viennent d'une base SQLite plutôt que d'un dossier :
c'est elle qu'édite l'[API HTTP](#api-http), et le passage la sert exactement comme le dossier
— même validation, même `--profil`, sortie sous `output/<id>/`. Elle est exclusive des trois
autres variables.

#### Le catalogue des catégories

Tout ce que contient le FreshRSS partagé n'est pas à tout le monde : une veille concurrentielle
d'entreprise ne doit être ni notée, ni résumée, ni montrée à quelqu'un d'extérieur. Le
**catalogue** décrit chaque catégorie FreshRSS — description lisible, métiers concernés,
visibilité — dans une table `categories` de la base des profils. Il s'écrit en JSON, hors du
dépôt (par exemple `input/categories.json`), sur le modèle de
[docs/categories.exemple.json](docs/categories.exemple.json) :

```json
{
  "_lisez_moi": ["Une entrée par catégorie FreshRSS. Absente d'ici : servie à personne."],
  "Tech generaliste": {"description": "Actualité tech large : langages, cloud, outils.", "metiers": ["developpeur", "cto"], "visibilite": "publique"},
  "Veille concurrentielle": {"description": "Concurrents et alertes du marché.", "metiers": ["cto"], "visibilite": "privee", "proprietaires": ["moi"]}
}
```

- la clé est le libellé FreshRSS, comparé rogné, sans casse ni accents ; une clé qui commence
  par `_` et dont la valeur est un texte ou une liste est un commentaire — avec un objet pour
  valeur, c'est une catégorie (`_Archive` en est une) ;
- `description` (texte non vide), `metiers` (liste de textes, libre pour l'instant) et
  `visibilite` sont exigés ; `publique` est servie à tout le monde, `privee` aux seuls
  `proprietaires` (des `username`, qui n'ont pas à exister déjà) ;
- une catégorie **absente** du catalogue n'est servie à personne : une catégorie créée dans
  FreshRSS n'apparaît chez personne tant qu'on ne l'a pas décrite, et une faute de recopie
  dans un libellé prive la catégorie de lecteurs au lieu de la donner à tous. Le passage
  le dit dans ses logs (`Catalogue : hors catalogue, servies à personne : …`) quand il
  marque la journée lue — pas lors d'un `--dry-run`, d'un `--no-mark-read` ni d'un
  `--profil` qui ne marque pas.

Il se charge dans la base par :

```bash
python -m rssresume.api importer-catalogue input/categories.json
```

Le fichier est validé **en entier** avant toute écriture — une clé inconnue, une visibilité
hors liste, une catégorie privée sans propriétaire ou publique avec, un propriétaire qui n'est
pas un nom de profil valide, deux libellés identiques une fois casse et accents retirés : rien
n'est écrit, le message nomme le libellé, code de sortie 2. Accepté, il **remplace** le
catalogue : une catégorie retirée du fichier disparaît de la base. Le passage revalide la table
à chaque lancement, et une ligne corrompue à la main le fait échouer.

Sans catalogue — pas de base, ou table vide —, tout est servi à tout le monde, comme avant :
c'est accepté pour **un seul profil**, avec un avertissement à chaque passage ; dès **deux
profils**, le passage refuse de démarrer (message d'erreur, code de sortie 2) et dit quoi faire :

- en base, importer le catalogue (`importer-catalogue`) ;
- avec un dossier de profils (`RSSRESUME_PROFILES_DIR`) ou un document unique, il n'existe
  **pas** de catalogue hors de la base : passer d'abord à la base — poser
  `RSSRESUME_PROFILES_DB`, `python -m rssresume.api importer <dossier>`, retirer
  `RSSRESUME_PROFILES_DIR` —, puis importer le catalogue. Une installation à plusieurs profils
  en mode dossier ne tourne donc plus tant que cette migration n'est pas faite.

Le catalogue dit *à qui* ; les variables d'environnement continuent de dire *quoi* et
*comment* :

| Variable | Avec le catalogue |
| --- | --- |
| `RSSRESUME_CATEGORIES` | restreint encore la sélection de l'installation ; le catalogue s'applique par-dessus |
| `RSSRESUME_EXCLUDED_CATEGORIES` | appliquée d'abord, pour tout le monde, sans casse ni accents ; redondante avec un catalogue, non dépréciée |
| `RSSRESUME_CERTFR_CATEGORIES` | dit *comment* traiter la catégorie ; elle doit figurer au catalogue pour être servie |
| `RSSRESUME_CATEGORY_THRESHOLDS` | inchangée, s'applique aux catégories servies |

Le marquage comme lu ne change pas : une catégorie servie à personne — hors catalogue, ou
privée sans propriétaire parmi les profils — est lue à la fin du passage pour être marquée
avec le reste, une fois, et seulement quand tout le monde a été servi. Si cette lecture
échoue, l'erreur est journalisée et ce qui a été servi est marqué quand même : les emails sont
partis, un rejeu ne doit pas les renvoyer.

`--send-only` renvoie les journaux déjà écrits sans les refiltrer : une journée produite avant
l'import du catalogue peut contenir des catégories devenues privées.

### Renvoyer l'email d'une journée

Une journée coûte du scoring, des résumés et de la synthèse vocale. Quand c'est l'envoi
seul qui a échoué — un port SMTP filtré, une clé refusée, un domaine non vérifié — la
repayer pour retrouver un texte déjà écrit sur le disque n'aurait aucun sens :

```bash
python -m rssresume --send-only --date 2026-08-29
```

Tout ce que l'email porte est relu de `output/<id>/<date>/*.log.json` : le résumé, les liens
des articles retenus dans l'ordre du digest, et les `.mp3` en pièces jointes. Ni FreshRSS
ni le moindre fournisseur n'est appelé, et **rien n'est marqué comme lu** — le renvoi ne
touche à aucun état.

Deux limites à connaître :

- une catégorie sans le moindre article n'écrit pas de journal — elle n'a rien lu ni rien
  dépensé — et sa ligne « aucun article » manque donc au corps du renvoi ;
- les journées produites avant que le journal ne garde le texte du résumé se renvoient
  sans lui : les liens et l'audio sont là, le texte est vide.

Dans le conteneur, la sortie est dans le volume et non dans `output` :

```bash
docker exec -it <conteneur> python -m rssresume --send-only --date 2026-08-29
```

### Suivre une journée dans le conteneur

Les journaux vivent dans le volume, sur un serveur où l'on n'entre que par SSH. Les en
extraire pour répondre à « qu'est-ce qui s'est passé ce matin » revient à lire un JSON de
plusieurs centaines de lignes. `--journal` le fait à votre place :

```bash
docker exec <conteneur> python -m rssresume --journal --date 2026-08-30
```

```
Journée du 2026-08-30 — /data/output/5f0c2d8e-7a1b-4c3d-9e8f-0a1b2c3d4e5f/2026-08-30
audio : journee.mp3 (montage)

catégorie                               statut                art.  ret.  seuil       coût
2 - Cybersecurite technique et menaces  monte                    6     4      5          ?
6 - Tech generaliste                    monte                    2     1      5          ?
7 - IA et R and D                       aucun-article-retenu     1     0      5   0.000225

Sans journal (aucun article lu) :
  1-alertes-et-avis-cert-fr-anssi.no-article
  3-conformite-reglementation-et-gouvernance.no-article

Consommation IA :
  scoring : 2 appel(s), 2530 token(s) en entrée, 119 en sortie
  montage : 1 appel(s), 2856 token(s) en entrée, 1128 en sortie
  total : 7 appel(s), …, coût inconnu : 1 modèle(s) sans tarif (gpt-5.6-luna)
```

Trois colonnes portent l'essentiel :

- **`seuil`** est celui qui a **réellement** trié, repli compris — pas celui de la
  configuration. C'est lui qui explique une journée maigre ;
- **`coût`** vaut `?` et non `0.000000` quand le modèle n'est pas dans la grille de
  tarifs : « on ne sait pas » et « rien dépensé » ne se lisent pas pareil ;
- **`statut`** distingue une catégorie vide (`aucun-article-retenu`) d'une catégorie
  montée dans l'audio de la journée (`monte`) d'une catégorie interrompue (`interrompu`).

`--debug` ajoute chaque article sous sa catégorie — score, thématique, retenu ou non, et
si sa note a été calculée ou relue des tags :

```
2 - Cybersecurite technique et menaces  monte                    6     4      5          ?
     9/10 cyber         retenu  tags      TerminalFix Uses Fake Cloudflare CAPTCHAs…
     4/10 autre                 tags      YARA-X 1.20.0 Release
```

La colonne d'origine est celle qui explique une journée qui n'a presque rien coûté : tout
relu des tags, aucun appel de scoring.

**Pour ne plus avoir à le demander**, `RSSRESUME_DEBUG=true` fait imprimer ce même bilan
à la fin de chaque passage : il atterrit dans la sortie standard, donc dans l'onglet Logs
de l'hébergeur, où il se cherche et s'archive tout seul. Rien n'est écrit de plus sur le
disque, et aucun appel n'est fait.

### Le document de la personne

Le profil de pertinence décide ce qui monte au-dessus du seuil, ce qui est raconté et sous quel
angle : les trois prompts l'utilisent — notation, résumé d'article, digest audio. La stack décide
quels avis CERT-FR font lever la tête. L'adresse décide où tout cela arrive. Les trois sont
personnelles, et **ne vont pas dans le dépôt** : elles tiennent dans un document unique, sous
`input/`, gitignoré.

```bash
RSSRESUME_PROFILE_FILE=input/moi/profile.json
```

```json
{
  "_note": "les clés inconnues servent à annoter, elles n'entrent nulle part",
  "profil": "CTO d'un SaaS B2B…\n\nAxes de veille pertinents :\n- reglementaire : …",
  "stack": ["Traefik", {"nom": "Keycloak", "alias": ["RH-SSO"]}],
  "email": "moi@example.com",
  "prenom": "Adrien"
}
```

Seule `profil` est exigée. `stack` absente, aucun avis n'est apparié et le digest le dit ;
`email` absente, aucun email ne part. `email` accepte une adresse ou une liste d'adresses.
`prenom` ne sert qu'à la salutation de l'audio en mode `global` : absente, le montage
ouvre sans nommer personne. Remplie avec autre chose qu'un texte, elle fait échouer le
lancement — une salutation qui se trompe ne se découvrirait qu'à l'écoute.
`id` est l'identifiant stable du profil, un UUID en minuscules (`5f0c2d8e-…`) : il nomme le
répertoire de sortie. Absent, il est généré et écrit dans le fichier au premier passage ;
présent mais mal formé, il fait échouer ce profil.

Le document doit être un **objet JSON** : un texte brut ne peut pas porter son `id`, et le profil
est alors sauté avec un message qui demande de le convertir.

Sans document déclaré, **rien ne tourne** : ni lecture FreshRSS, ni résumé, ni email — le
passage journalise « aucun profil ». `RSSRESUME_PROFILE`, le profil en clair sur une ligne,
n'est plus lue : posée, elle fait échouer le lancement, pour qu'on la remplace par un document.

Le document est résolu **une fois au démarrage** : annoncé mais illisible, vide, au JSON cassé,
sans texte à la clé `profil`, avec une entrée de stack fautive ou une adresse qui n'en est pas
une, il fait échouer le lancement plutôt que de retomber en silence sur un autre profil. Et comme l'empreinte de scoring inclut le profil, en changer renote
automatiquement les articles concernés : aucun score calculé contre l'ancien profil ne survit —
sortir un profil du code vers un fichier ne coûte donc rien tant que le texte est repris à
l'identique.

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

- sans `RSSRESUME_CATEGORIES`, toutes les catégories FreshRSS détectées sont traitées — pour
  chaque profil, celles que le [catalogue](#le-catalogue-des-catégories) lui sert.
- `RSSRESUME_EXCLUDED_CATEGORIES` retire des catégories de la liste traitée (comparaison insensible à la casse et aux accents).
- tester le scoring seul sur trois articles en dur, sans FreshRSS ni email :
  `python -m rssresume.llm.processing` (nécessite la clé du fournisseur actif, `OPENAI_API_KEY` par défaut).

## Déploiement quotidien (conteneur, Dokploy)

Le conteneur ne sert rien et n'écoute sur aucun port : il dort jusqu'à l'heure dite,
envoie le digest de la veille, et se rendort. C'est [`rssresume/scheduler.py`](rssresume/scheduler.py)
qui tient la boucle — pas un `cron`, qui n'hérite ni des variables d'environnement du
conteneur ni de `RSSRESUME_TIMEZONE`.

| Variable | Effet | Défaut |
| --- | --- | --- |
| `RSSRESUME_SCHEDULE` | heure du passage, dans `RSSRESUME_TIMEZONE` | `07:00` |
| `RSSRESUME_SCHEDULE_DAYS_BACK` | journée digérée, comptée depuis celle du passage | `1` (la veille) |

`DAYS_BACK` n'est pas un détail : à 7 h du matin, « aujourd'hui » ne contient que les
articles parus depuis minuit. Un passage du matin raconte la veille (`1`) ; un passage
du soir raconte la journée qui s'achève (`0`).

Une journée qui échoue — FreshRSS injoignable, fournisseur en panne — est journalisée
et la boucle continue. Un conteneur arrêté au moment du passage ne le rattrape pas : le
suivant a lieu le lendemain à la même heure.

### L'image

[`Dockerfile`](Dockerfile) : `python:3.14-alpine`, la base de fuseaux d'Alpine, et
`rssresume/`. Rien d'autre — pas de `pip` dans le résultat, puisqu'il n'y a rien à
installer. La sortie va dans `/data`, monté en volume : `RSSRESUME_OUTPUT_DIR` y est
déjà pointé par l'image.

`espeak` n'est pas installé : c'est le repli de la synthèse vocale quand aucune clé
d'API n'est configurée, et un déploiement qui envoie un digest audio en a forcément une.
L'ajouter, si besoin : `apk add --no-cache espeak`.

### Dokploy

1. **Create Service → Compose**, dépôt Git de ce projet, `docker-compose.yml` à la racine.
2. Onglet **Environment** : y coller le contenu de son `.env` local — clés FreshRSS,
   clés d'API, SMTP, seuils, `RSSRESUME_SCHEDULE`. C'est le seul endroit où les secrets
   sont saisis, et ils ne passent jamais par le dépôt.
3. **Deploy**. Aucun domaine à déclarer : le service n'expose rien.

Le chemin d'une variable, de Dokploy jusqu'à `AppConfig.from_env()` :

```
onglet Environment  →  .env à la racine du projet  →  env_file:  →  environnement du
                       (écrit par Dokploy)             (compose)     processus Python
```

Le bloc `environment:` du compose ne sert qu'à deux choses par-dessus : poser les
défauts de l'horaire, et imposer `RSSRESUME_OUTPUT_DIR=/data`. Il l'emporte sur
`env_file`, ce qui est voulu : un `RSSRESUME_OUTPUT_DIR=output` recopié du poste de
travail ferait sinon écrire le conteneur dans `/app`, que l'utilisateur non-root ne
possède pas — et la sortie du jour n'atterrirait pas dans le volume.

Le compose impose aussi `RSSRESUME_PROFILES_DB=/data/profils.sqlite3` : les profils vivent
en base dans le volume, là où l'API les édite (voir [API HTTP](#api-http)). La base remplace
le dossier `/data/profils` : `RSSRESUME_PROFILES_DIR`, `RSSRESUME_PROFILE_FILE` et
`RSSRESUME_PROFILE` doivent **quitter** l'onglet Environment — posées avec la base, elles font
échouer le lancement. Migrer des documents existants, une fois, puis retirer la variable :

```bash
docker cp input/moi/profile.json <conteneur>:/data/profils/adrien.json
docker exec <conteneur-api> python -m rssresume.api importer /data/profils
```

L'import conserve l'`id` des documents (il en génère un sinon, et l'affiche), ne modifie pas
les fichiers, et se rejoue sans rien réécrire. Tant qu'il n'a pas eu lieu, la base est vide
et le passage ne sert personne.

Dès que la base compte deux profils, le passage exige le
[catalogue des catégories](#le-catalogue-des-catégories) : l'importer avant — ou en même temps
que — la mise en production, sans quoi le passage refuse de démarrer :

```bash
docker cp input/categories.json <conteneur-api>:/data/categories.json
docker exec <conteneur-api> python -m rssresume.api importer-catalogue /data/categories.json
```

`input/` **n'entre pas dans l'image** : [.dockerignore](.dockerignore) ne laisse passer que
`rssresume/`, et le répertoire est gitignoré, donc absent du dépôt que Dokploy clone.

Un document fautif ou un fichier mal nommé ne coûtent que la journée de leur personne, et se
lisent dans les logs ; un dossier absent fait échouer le lancement — un conteneur qui ne démarre
pas se voit, un matin sans digest non. Les actions manuelles du déploiement sont listées dans
[todo-dockploy.md](todo-dockploy.md).

Les logs de Dokploy montrent l'heure du prochain passage, puis le suivi d'exécution du
digest. Pour rejouer une journée à la main, sans attendre l'heure :

```bash
docker exec -it <conteneur> python -m rssresume --date 2026-08-23
```

## API HTTP

Le site qui édite les profils et fait écouter les journées parle à un second processus,
`python -m rssresume.api` — le service `api` du compose, même image, même volume. Il ne lance
aucun digest et n'appelle aucun fournisseur : il écrit la base que le passage relit, et sert
les audios que le passage a écrits. Bibliothèque standard seulement (`http.server`, `sqlite3`).

| Variable | Effet | Défaut |
| --- | --- | --- |
| `RSSRESUME_API_TOKEN` | jeton exigé en `Authorization: Bearer …` ; absent ou < 32 caractères, le serveur ne démarre pas | — |
| `RSSRESUME_PROFILES_DB` | la base des profils (obligatoire pour l'API) | — |
| `RSSRESUME_OUTPUT_DIR` | où lire les journées, `<id>/<date>/` | `output` |
| `RSSRESUME_API_HOST` / `RSSRESUME_API_PORT` | adresse d'écoute | `0.0.0.0` / `8080` |

Toutes les routes exigent le jeton (401 sinon). Réponses en JSON UTF-8 ; une erreur est
`{"erreur": "…"}`, avec 400, 401, 404, 405, 409, 413, 416 ou 422.

| Méthode et route | Réponse |
| --- | --- |
| `GET /api/v1/profils` | `[{"id","username","prenom","email","modifie_le"}]`, trié par nom |
| `POST /api/v1/profils` | corps `{"username","profil","stack","email","prenom"}` → 201 profil complet, id généré ; 409 nom pris ; 422 invalide |
| `GET /api/v1/profils/{username}` | `{"id","username","profil","stack","email","prenom","modifie_le"}` ; 404 |
| `PUT /api/v1/profils/{username}` | corps `{"profil","stack","email","prenom"}` → 200 ; 404 ; 422 (id et nom ne changent pas) |
| `DELETE /api/v1/profils/{username}` | 204 ; 404 — les journées restent sur le disque |
| `GET /api/v1/profils/{username}/journees` | `[{"date","audios":[{"nom","taille"}]}]`, la plus récente d'abord |
| `GET /api/v1/profils/{username}/journees/{date}/audios/{nom}` | l'audio (`audio/mpeg` ou `audio/wav`), 200 ou 206 avec `Range`, 416 hors du fichier |
| `GET /api/v1/profils/{username}/journees/{date}` | le contenu de la journée relu de ses journaux, comme `--send-only` : résumés, articles « à lire » et « à surveiller » (`url` à `null` hors http(s)), audios, `raison` d'une journée sans article ; 404 |
| `GET /api/v1/passage` | `{"heure","fuseau","prochain"}`, lus de `RSSRESUME_SCHEDULE` et `RSSRESUME_TIMEZONE` comme le travailleur |

Un document est validé par `profil_depuis_dict`, la fonction même que le passage appelle : l'API
refuse exactement ce que la tournée refuserait, avec le même message. Le corps d'une écriture
est limité à 64 Kio (413) et doit être `application/json`.

Pour l'essayer en local :

```bash
RSSRESUME_PROFILES_DB=input/profils.sqlite3 RSSRESUME_API_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(48))") \
  python -m rssresume.api
python -m rssresume.api importer input/profils    # migrer des documents JSON, une fois
python -m rssresume.api importer-catalogue input/categories.json    # remplacer le catalogue
```

## Organisation du code

Un module par thème technique, dans [rssresume/](rssresume/) :

| Module | Rôle |
| --- | --- |
| `cli.py` | arguments, assemblage des composants, `main()` |
| `scheduler.py` | boucle quotidienne : attend l'heure dite, lance le digest de la veille |
| `config.py` | configuration lue depuis l'environnement |
| `models.py` | objets métier (`Article`, `CategoryDigest`) |
| `protocols.py` | contrats des collaborateurs de `DigestService` |
| `profil.py` | le document de la personne : profil de pertinence, stack, destinataire |
| `annuaire_sqlite.py` | `AnnuaireSqlite` : les profils en base SQLite, lus par la tournée, écrits par l'API ; le catalogue des catégories |
| `categories.py` | `Catalogue` : à qui chaque catégorie FreshRSS est servie, publique ou privée |
| **`api/`** | **l'API HTTP du site** (`python -m rssresume.api`) |
| `api/serveur.py` | serveur, jeton, corps JSON, envoi des audios par plages |
| `api/routes.py` | une classe par forme d'URL |
| `api/sorties.py` | les journées et les audios d'un profil, lus sur le disque sans en sortir |
| `api/importation.py` | migration d'un dossier de profils JSON vers la base |
| `digest.py` | orchestration du digest quotidien |
| `summaries.py` | résumé d'une catégorie : celui du fournisseur, ou le repli extractif |
| `montage.py` | le texte d'un seul audio pour la journée, en mode `global` |
| `audio.py` | synthèse vocale (fournisseur configuré, ou `espeak`), découpée si le texte dépasse |
| `pricing.py` | lecture de la grille de tarifs et calcul du coût d'un appel |
| `runlog.py` | journal `<categorie>.log.json` : articles, scores et coûts par catégorie |
| **`certfr/`** | **la catégorie qui ne passe par aucun modèle** |
| `certfr/stack.py` | ce qu'est un composant surveillé, et l'appariement d'un texte d'avis |
| `certfr/service.py` | tri d'une journée d'avis : criticité, classement, phrase produite |
| **`external/`** | **les systèmes que l'on ne contrôle pas** |
| `external/freshrss.py` | client de l'API Google Reader de FreshRSS (lecture, tags, marquage comme lu) |
| `external/mailer.py` | construction et envoi de l'email |
| **`llm/`** | **tout ce qui parle à un modèle** |
| `llm/providers.json` | réglages non secrets de chaque fournisseur : endpoint, modèles, voix, tarifs |
| `llm/providers.py` | lecture de ces réglages, et choix du fournisseur par action |
| `llm/prompts.py` | les prompts, indépendants de tout fournisseur |
| `llm/base.py` | `LLMProvider` : les opérations, le transport, et la fabrique |
| `llm/openai.py` | `OpenAIProvider` : ce que le dialecte OpenAI change |
| `llm/mistral.py` | `MistralProvider` : idem, dont la synthèse `voice_id` / base64 |
| `llm/processing.py` | relecture des réponses du noteur, et démonstration autonome |
| **`tools/`** | **ce qui ne parle ni de veille, ni de FreshRSS, ni de modèles** |
| `tools/console.py` | suivi d'exécution affiché dans la console |
| `tools/text.py` | nettoyage de HTML, slugs, et quelques phrases toutes faites |
| `tools/cve.py` | lecture de la page d'un avis de vulnérabilité, quand le flux n'en dit rien |
| `tools/http.py` | réessai des appels réseau : backoff, jitter, `Retry-After` |

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
  résumé via openai — gpt-5.6-luna (5 article(s), 31428 caractère(s) envoyés, 1 tronqué(s) à 8000)
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
python -m unittest discover
```