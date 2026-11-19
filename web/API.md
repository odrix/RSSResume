# Contrat de l'API de résumé

L'appli de résumé (Python) possède les **profils** et les **journées** ; le site
d'administration (`web/`) possède les **comptes** et les sessions. Le site appelle cette
API depuis son serveur uniquement : le navigateur ne la voit jamais, le jeton non plus.

Ce document est la référence des deux côtés. Côté site, il est implémenté dans un seul
module, [`src/lib/server/api-resume.ts`](src/lib/server/api-resume.ts), et simulé par
[`mock/faux-api.js`](mock/faux-api.js) (tests et `npm run mock`).

## Généralités

- **Base** : `RSSRESUME_API_URL`, `http://api:8080` sur le réseau compose — un service
  `api` à part, même image que `rssresume`, lancé par `python -m rssresume.api`.
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

En sortie, `email` est toujours une liste et `prenom` toujours une chaîne, même si le
document stocké avait une adresse seule ou pas de prénom.

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

Corps : `{"username", "profil", "stack": [...], "email": [...], "prenom"}`.

- `201` → le profil complet (forme ci-dessus)
- `409` → username déjà pris
- `422` → username ou champ invalide

### `GET /api/v1/profils/{username}`

- `200` → `{"id", "username", "profil", "stack", "email", "prenom", "modifie_le"}`
- `404`

### `PUT /api/v1/profils/{username}`

Corps : `{"profil", "stack", "email", "prenom"}` — remplacement complet, pas de fusion.

- `200` → le profil complet, `modifie_le` mis à jour, `id` inchangé
- `404`, `422`

### `DELETE /api/v1/profils/{username}`

- `204`, sans corps
- `404`

Le site l'appelle pour défaire une inscription dont le compte n'a pas pu être créé.

### `GET /api/v1/profils/{username}/journees`

→ `200`, les journées qui ont produit de l'audio, **date décroissante** :

```json
[{"date": "2026-11-18", "audios": [{"nom": "journee.mp3", "taille": 12345}]}]
```

`taille` en octets. `404` si le profil n'existe pas ; `[]` s'il n'a encore rien produit.

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
