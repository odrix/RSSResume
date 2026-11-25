# Contrat de l'API de résumé

L'appli de résumé (Python) possède les **profils** et les **journées** ; le site
d'administration (`web/`) possède les **comptes** et les sessions. Le site appelle cette
API depuis son serveur uniquement : le navigateur ne la voit jamais, le jeton non plus.

Ce document est la référence des deux côtés. Côté site, il est implémenté dans un seul
module, [`src/lib/server/api-resume.ts`](src/lib/server/api-resume.ts), et simulé par
[`mock/faux-api.js`](mock/faux-api.js) (tests et `npm run mock`).

## Généralités

- **Base** : `RSSRESUME_API_URL`, `http://rssresume-api:8080` — le service `api` du compose
  de l'appli de résumé (même image que `rssresume`, lancé par `python -m rssresume.api`),
  joint par son alias sur `dokploy-network`, le site étant une application Dokploy distincte.
- **Authentification** : chaque requête porte `Authorization: Bearer ${RSSRESUME_API_TOKEN}`.
  Jeton absent ou faux → `401`.
- **Corps** : JSON UTF-8 (`Content-Type: application/json`), sauf l'audio.
- **Dates** : `modifie_le` en ISO 8601 avec fuseau (`2026-11-19T07:00:00+00:00`) ; une
  journée en `YYYY-MM-DD`.
- **Username** : `^[a-z0-9][a-z0-9_-]{1,31}$`. C'est l'identifiant du profil, et le même
  que celui du compte sur le site. Il apparaît encodé (`encodeURIComponent`) dans les chemins.
- **Erreurs** : corps `{"erreur": "message lisible"}`, statuts `400`, `401`, `404`, `409`,
  `422`. Le message d'un `422` est **affiché tel quel** à la personne dans « Mon profil » :
  il doit être en français et dire quel champ est en cause (`email : adresse invalide (x)`).
  Quand le refus tient à une clé du profil, le corps la nomme aussi :
  `{"erreur": "…", "champ": "categories"}` — `profil`, `stack`, `email`, `prenom`, `securite`,
  `axes`, `categories`, `flux_exclus` ou `id`. Le site affiche alors le message sous ce champ ;
  sans `champ`, ou pour un champ que la page ne montre pas, en tête de page. Un catalogue
  des catégories illisible en base est une panne, pas un refus : `500`, sans `champ`.

## Ce que le site garantit à l'API

- Un profil n'est créé (`POST`) qu'une fois l'adresse du compte confirmée par un lien.
- `email` ne contient que des adresses confirmées : celle du compte, et celles dont le
  titulaire a ouvert le lien de confirmation. Une adresse en attente reste dans la base du
  site et n'est jamais envoyée.

## Le profil

Le document de la personne, au format de `rssresume/profil.py` :

```json
{
  "id": "3f2b8c1e-7d4a-4e9b-a0c5-1b2d3e4f5a6b",
  "username": "adrien",
  "profil": "CTO d'un SaaS B2B…\n\nAxes de veille pertinents :\n- …",
  "stack": ["Traefik", {"nom": "Keycloak", "alias": ["RH-SSO"]}],
  "email": ["moi@example.com"],
  "prenom": "Adrien",
  "securite": "exploitant",
  "modifie_le": "2026-11-19T07:00:00+00:00"
}
```

| Clé      | Type                                            | Règle                                      |
| -------- | ----------------------------------------------- | ------------------------------------------ |
| `id`     | UUID (texte)                                    | attribué par l'API à la création, immuable ; **en sortie seulement** |
| `profil` | texte                                           | exigé, non vide                            |
| `stack`  | liste de `"Nom"` ou `{"nom", "alias": [texte]}` | peut être vide                             |
| `email`  | liste d'adresses                                | toujours une **liste** en sortie ; vide = aucun envoi |
| `prenom` | texte                                           | `""` quand absent                          |
| `securite` | `"exploitant"`, `"decideur"` ou `"curieux"`   | `"exploitant"` quand absent ; toute autre valeur → `422` |

| `flux_exclus` | liste de titres de flux FreshRSS            | ni notés ni résumés, marqués lus quand même ; titre exact, casse et accents ignorés ; absente de la réponse quand vide ; entrée vide ou doublon → `422` |
| `axes`   | liste de `{"slug", "libelle", "description"}`  | facultatif ; absent ou `[]` = les rubriques par défaut ; 3 à 6 axes, slug `^[a-z][a-z0-9-]{1,23}$` |
| `categories` | liste de noms de catégories                 | facultatif ; absent ou `[]` = tout ce que le catalogue autorise, futures comprises ; une catégorie inconnue ou privée d'autrui → `422` (`champ: "categories"`) ; en `PUT`, absent = l'abonnement stocké est gardé (fusion), un `null` explicite remet à « tout » ; seules les catégories **ajoutées** sont vérifiées, celles déjà suivies passent même retirées du catalogue depuis (la tournée les refiltre) |


En sortie, `email` est toujours une liste et `prenom` toujours une chaîne, même si le
document stocké avait une adresse seule ou pas de prénom. `axes` et `categories` n'y
figurent que si le profil les déclare.

Le site les recopie d'un gabarit à la confirmation du compte, et « Mon profil » les édite :
des cases pour les catégories proposées (voir `GET …/categories`), six lignes libellé +
description pour les axes. Un axe existant garde son slug, un nouveau en reçoit un tiré de
son libellé ; toutes les lignes vides envoient `axes: []`. Toutes les catégories cochées
envoient `categories: null` : l'API retire la clé, pour que le profil suive aussi celles
ajoutées plus tard. Aucune cochée est refusé par le site avant l'appel, l'API lisant `[]`
comme « tout » — en `PUT`, un `null` dit la même chose. Une section que la page n'a pas pu
montrer (catalogue injoignable ou ouvert) garde la valeur lue : le `PUT` fusionne, la clé
que le site n'envoie pas n'est pas touchée par l'enregistrement.

`id` figure dans toutes les réponses qui portent un profil (la liste, `GET`, `POST`, `PUT`).
Les URL restent adressées par **username** ; le site n'envoie jamais `id` (ni `modifie_le`)
dans un corps `POST` ou `PUT`, et l'API ignore ces clés si elles y figurent.

## Points d'entrée

### `GET /api/v1/profils`

→ `200`, tous les profils, sans le texte ni la stack :

```json
[{"id": "3f2b8c1e-…", "username": "adrien", "prenom": "Adrien", "email": ["moi@example.com"], "modifie_le": "…"}]
```

### `POST /api/v1/profils`

Corps : `{"username", "profil", "stack": [...], "email": [...], "prenom", "securite"}`, et
`"axes"`, `"categories"` quand le profil part d'un gabarit. La création ne fusionne rien :
absent et liste vide y valent tous deux le défaut.

- `201` → le profil complet (forme ci-dessus)
- `409` → username déjà pris
- `422` → username ou champ invalide

### `GET /api/v1/profils/{username}`

- `200` → `{"id", "username", "profil", "stack", "email", "prenom", "securite", "modifie_le"}`,
  plus `axes` et `categories` quand le profil les déclare
- `404`

### `PUT /api/v1/profils/{username}`

Corps : les clés à changer — `{"profil", "stack", "email", "prenom", "securite"}`, et
`"axes"`, `"categories"`, `"flux_exclus"` quand le client les édite. Fusion, pas
remplacement : une clé absente du corps garde sa valeur stockée, une clé présente la
remplace, un `null` explicite la remet à son défaut (absente du document — pour `email`,
`axes`, `categories` et `flux_exclus`, « aucun réglage » / « tout le catalogue »). Le site
n'envoie que les clés qu'il édite : un réglage déclaré par l'API ou par un gabarit survit
ainsi à un enregistrement qui ne le connaît pas.

- `200` → le profil complet, `modifie_le` mis à jour, `id` inchangé
- `404`, `422` (avec `champ` quand une clé est en cause)

### `GET /api/v1/profils/{username}/categories`

→ `200`, les catégories que ce username peut suivre — publiques, et privées dont il est
propriétaire —, dans l'ordre du catalogue :

```json
{"ouvert": false, "categories": [{"libelle": "Cybersécurité", "description": "…", "privee": false}]}
```

- Jamais les propriétaires ni les métiers : la page n'en a pas l'usage, et une catégorie
  privée d'autrui n'apparaît pas du tout. La règle est celle qui refuse l'enregistrement.
- `ouvert: true` et `categories: []` quand aucun catalogue n'est déclaré : tout est suivi,
  il n'y a rien à cocher.
- Le profil n'a pas à exister (la page s'affiche avant le premier enregistrement) ; `404`
  pour un username invalide.

Le site l'appelle à chaque affichage de « Mon profil », sans cache ; injoignable, la section
des catégories est masquée et la clé n'est pas envoyée.

### `DELETE /api/v1/profils/{username}`

- `204`, sans corps
- `404`

Le site ne l'appelle pas aujourd'hui (le profil n'est créé qu'à la confirmation du compte) ;
il fait partie du contrat pour l'administration à venir.

### `GET /api/v1/profils/{username}/journees`

→ `200`, toutes les journées produites, **date décroissante** :

```json
[{"date": "2026-11-18", "audios": [{"nom": "journee.mp3", "taille": 12345}]}]
```

`taille` en octets. Une journée sans audio (aucun article, ou rien de retenu) est listée
avec `"audios": []`. `404` si le profil n'existe pas ; `[]` s'il n'a encore rien produit.

### `GET /api/v1/profils/{username}/journees/{date}`

Le contenu de la journée, relu de ses journaux exactement comme `--send-only` le relit pour
renvoyer l'email :

```json
{
  "date": "2026-11-21",
  "audios": [{"nom": "cyber.mp3", "taille": 12345}],
  "ecoute": "21 min",
  "racontees": 3,
  "montage": {"audio": "journee.mp3", "ecoute": "12 min"},
  "raison": null,
  "en_cours": false,
  "categories": [{
    "categorie": "Cybersécurité", "racontee": true, "resume": "…",
    "audio": "cyber.mp3", "ecoute": "5 min",
    "articles": [{"titre": "…", "source": "…", "url": "https://…"}],
    "a_surveiller": [{"titre": "…", "source": "…", "url": null}]
  }]
}
```

- `montage` vaut `null` en mode par catégorie ; `audio` et `ecoute` y valent `null` quand le
  fichier manque ou que sa durée ne se mesure pas.
- `raison` : la phrase d'une journée sans article (`categories` vide), `null` sinon.
- `en_cours` : `true` quand la tournée écrit encore la journée — aucun journal ni marqueur
  `.no-article` encore, ou un journal tronqué lu en pleine écriture. `categories` est alors
  vide et `raison` à `null` : la journée n'est pas vide, elle n'est pas finie.
- Les textes (`resume`, `titre`, `source`) sont **bruts** : ils viennent du modèle et des flux,
  le site les échappe au rendu.
- `url` vaut `null` pour tout lien qui n'est pas `http` ou `https` (`javascript:`, `data:`…) :
  le site n'en fait alors pas un lien, et refait le même contrôle de son côté.
- `404` → profil ou journée inconnus, date mal formée.

### `GET /api/v1/passage`

→ `200`, l'heure du passage quotidien et le prochain, lus des mêmes variables que le
travailleur (`RSSRESUME_SCHEDULE`, `RSSRESUME_TIMEZONE`) :

```json
{"heure": "04:00", "fuseau": "Europe/Paris", "prochain": "2026-11-23T04:00:00+01:00"}
```

### `GET /api/v1/profils/{username}/journees/{date}/audios/{nom}`

Le fichier MP3, en flux.

- `200` → `Content-Type: audio/mpeg`, `Content-Length`, `Accept-Ranges: bytes`
- `206` → si la requête porte `Range: bytes=a-b` (ou `a-`, ou `-n`) : `Content-Range: bytes a-b/total`,
  `Content-Length` de la plage
- `416` → plage hors du fichier, avec `Content-Range: bytes */total`
- `404` → profil, journée ou fichier inconnu

`nom` est un nom de fichier (`^[A-Za-z0-9][A-Za-z0-9._-]*\.mp3$`), jamais un chemin : l'API
doit refuser tout `..` ou séparateur plutôt que de le résoudre. `ETag` et `Last-Modified`
sont facultatifs ; s'ils sont présents, le site les relaie.

Le site relaie `Range` tel quel et recopie statut et en-têtes : sans `206`, un lecteur
`<audio>` ne peut pas avancer dans un fichier qu'il n'a pas fini de télécharger.

### `POST /api/v1/desabonnements/lecture`

Corps `{"jeton": "…"}`, le dernier segment du lien de désabonnement de la lettre
(`/desabonnement/{jeton}`). → `200`, ce que le lien désabonnerait, **sans rien modifier** :

```json
{"username": "bea", "destinataires": 2}
```

- `404` → `{"erreur": "Lien de désabonnement invalide ou déjà utilisé."}`, quelle qu'en soit la
  raison : jeton illisible, signature fausse, profil supprimé, ou plus aucune des adresses de
  la lettre parmi les destinataires. Une liste qui a changé depuis l'envoi garde le lien
  valable tant qu'il y reste au moins une adresse de la lettre.

Un `POST` et non un `GET` : le jeton voyage dans le corps, hors des chemins que l'API
journalise. Le site l'appelle pour afficher la page du lien ; un antivirus de messagerie qui
ouvre le lien ne désabonne donc personne.

### `POST /api/v1/desabonnements`

Corps `{"jeton": "…"}`. → `200 {"username": "bea"}` : les destinataires du profil sont vidés
(la clé `email` du document est retirée).

- `404` → même message que la lecture. Un lien ne sert qu'une fois : il porte une empreinte
  de chaque adresse de la lettre, et aucune ne correspond plus une fois les destinataires retirés.

Le jeton compte huit caractères par destinataire de la lettre, en plus d'environ 85 : le site
en borne la longueur à 4 096.

Le site ne vérifie pas le jeton, il ne connaît pas la clé : il le relaie tel quel, sans
session ni cookie. C'est la seule route du site qui accepte un `POST` d'une autre origine — le
désabonnement en un clic (`List-Unsubscribe-Post`) que Gmail et Yahoo envoient depuis le
client mail (`web/src/lib/server/csrf.ts`).

### Les retours « utile / pas utile »

Un vote par profil et par journée : le second remplace le premier, qu'il vienne du lien de la
lettre ou de la page des résumés. Un retour a cette forme :

```json
{"username": "bea", "jour": "2026-11-22", "avis": "pas_utile", "commentaire": "Trop long.", "vote_le": "2026-11-23T07:12:03+00:00"}
```

- `avis` : `utile` ou `pas_utile`.
- `commentaire` : texte brut, rogné, fins de ligne ramenées à `\n`, **2 000 caractères** au
  plus (comptés en points de code : un emoji vaut un). Au-delà, refusé — jamais tronqué. Le
  site l'échappe au rendu.
- `vote_le` : posé par l'API, en UTC.
- `username` : `null` quand le profil a été supprimé depuis ; le retour reste.

Un refus de saisie est un `422` qui nomme son champ : `{"erreur": "…", "champ": "avis"}` ou
`"champ": "commentaire"`.

#### `POST /api/v1/retours/lecture`

Corps `{"jeton": "…"}`, le dernier segment du lien de vote de la lettre
(`/retour/{jeton}?avis=utile`), sans le paramètre. → `200`, la journée que le lien désigne et
le vote déjà donné, **sans rien écrire** :

```json
{"username": "bea", "jour": "2026-11-22", "retour": null}
```

- `404` → `{"erreur": "Lien de vote invalide."}`, quelle qu'en soit la raison : jeton illisible,
  signature fausse — un jeton de désabonnement compris —, date impossible ou profil supprimé.

Le jeton est `v1.<profil_id>.<AAAA-MM-JJ>.<signature>`, signé avec `RSSRESUME_API_TOKEN` sous
une clé propre au vote. La date est celle de la journée **racontée** (le titre de la lettre),
pas celle de l'envoi. Il n'expire pas. L'avis n'est pas signé : il passe en paramètre de l'URL
du site, et ne sert qu'à pré-cocher le formulaire.

#### `POST /api/v1/retours`

Corps `{"jeton": "…", "avis": "utile", "commentaire": "…"}` (`commentaire` facultatif). →
`200 {"username", "jour", "retour"}`, le vote enregistré. Le profil et la journée viennent du
seul jeton : un `profil_id`, `jour` ou `username` glissé dans le corps est ignoré.

- `404` → même message que la lecture.
- `422` → avis inconnu ou commentaire trop long, avec `champ`.

#### `GET /api/v1/retours`

→ `200`, les 200 retours les plus récents, du plus récent au plus ancien. Sans autre garde
que le jeton de l'API : c'est le site qui la réserve à l'administration (`/admin`).

#### `GET /api/v1/profils/{username}/journees/{date}/retour`

→ `200`, le vote déjà donné sur la journée. `404` → profil inconnu, date mal formée, ou aucun
vote.

#### `PUT /api/v1/profils/{username}/journees/{date}/retour`

Corps `{"avis": "…", "commentaire": "…"}`. → `200`, le retour enregistré ; `422` avec `champ`.
L'API ne vérifie pas que la journée existe sur le disque : le site ne propose de voter que sur
une journée qu'il vient d'afficher, à son propriétaire seulement — un administrateur qui
consulte la journée d'un autre ne vote pas.

Ouvrir le lien de la lettre n'enregistre rien : la page `/retour/{jeton}` montre le
formulaire, et seul son envoi vote. Contrairement au désabonnement, elle garde la protection
CSRF du site : le vote ne vient que de son propre formulaire.

### `GET /api/v1/gabarits`

→ `200`, les gabarits métier disponibles, triés par identifiant :

```json
[{"metier":"cto","libelle":"CTO, direction technique","profil":"…","securite":"decideur","axes":[…],"categories":[…]}]
```

Chaque gabarit est un document de départ. Il peut être affiché puis modifié librement avant
création du profil ; l’identifiant `metier` n’est pas stocké avec le profil.

Le site s'en sert deux fois : pour la liste du formulaire d'inscription (métier, libellé,
texte, catégories), puis à l'envoi du formulaire, pour copier le texte, la stack, le régime,
les axes et les catégories du métier choisi dans le compte en attente. « Mon profil » s'en
sert aussi : « Repartir d'un gabarit » (`/profil?gabarit=<metier>`) pré-remplit le texte, le
régime, les axes et les catégories sans rien enregistrer, et le texte d'un gabarit y sert
d'exemple. Il garde la liste
cinq minutes en mémoire (jamais une erreur). Le profil créé à la confirmation reprend cette
copie : la personne reçoit ce qu'elle a vu, même si le catalogue a changé entre-temps.
