# Déployer les profils multiples et l'API sur Dokploy

Actions manuelles, dans l'ordre. Cocher au fur et à mesure, vider le fichier une fois fait.
`<conteneur>` : le nom du conteneur `rssresume` (`docker ps --format '{{.Names}}' | grep rssresume`).
`<conteneur-api>` : celui du service `api` (même commande, il contient `api`).

Les profils vivent désormais **en base** (`/data/profils.sqlite3`, imposée par `docker-compose.yml`
aux deux services) et non plus dans le dossier `/data/profils`. Le dossier ne sert plus que de
source à l'import, puis de sauvegarde : l'import ne modifie pas les fichiers.

## Avant de redéployer (conteneur actuel encore en marche)

- [ ] Déposer le document de profil actuel dans le volume, sous son nom (`adrien`) — depuis la
      machine qui l'a, après l'avoir posé sur le VPS (`scp input/moi/profile.json vps:/tmp/adrien.json`).
      Il doit être un objet JSON (`{"profil": "…", …}`) :
      `docker exec -u root <conteneur> sh -c 'mkdir -p /data/profils && chown rssresume:rssresume /data/profils'`
      `docker cp /tmp/adrien.json <conteneur>:/data/profils/adrien.json`
      `docker exec -u root <conteneur> chown rssresume:rssresume /data/profils/adrien.json`
- [ ] Générer le jeton de l'API, sur n'importe quelle machine :
      `python -c "import secrets;print(secrets.token_urlsafe(48))"`

## Onglet Environment

- [ ] Ajouter `RSSRESUME_API_TOKEN=<le jeton>`. Le compose donne le même `.env` aux deux services,
      `rssresume` et `api` : une seule ligne suffit. Sans elle (ou avec moins de 32 caractères),
      le service `api` refuse de démarrer.
- [ ] Retirer `RSSRESUME_PROFILE_FILE`, `RSSRESUME_PROFILE` et `RSSRESUME_PROFILES_DIR` s'ils y sont :
      posés avec la base, ils font échouer le lancement des deux services.
- [ ] Ne pas ajouter `RSSRESUME_PROFILES_DB` ni `RSSRESUME_OUTPUT_DIR` : imposées par le compose.
- [ ] Retirer le montage `./input/moi:/config:ro` s'il avait été ajouté au compose.

## Côté site

- [ ] Poser le même jeton dans l'Environment du site, et l'URL de l'API : `http://api:8080`
      (nom du service). Ce nom ne se résout que si le site est sur le même réseau que le compose :
      si le site est une application Dokploy distincte, rattacher le service `api` au réseau
      `dokploy-network` (ou déployer le site dans le même compose). Aucun port n'est publié.

## Juste après le redéploiement (avant le premier passage, 4 h)

- [ ] Logs de `api` : `API RSSResume : écoute sur 0.0.0.0:8080`. Une erreur `RSSRESUME_API_TOKEN
      absente ou trop courte` renvoie à l'onglet Environment.
- [ ] Logs de `rssresume` : `RSSResume : 0 profil(s) : (aucun)` — normal, la base est vide. Une erreur
      `… sont posées ensemble` renvoie à l'onglet Environment.
- [ ] Importer les profils dans la base (idempotent, les fichiers ne sont pas modifiés) :
      `docker exec <conteneur-api> python -m rssresume.api importer /data/profils`
      La sortie donne l'identifiant : `Import : adrien → <id>`. Si le document portait déjà un `id`
      (écrit par un passage précédent), c'est celui-là qui est conservé.
- [ ] Ranger les anciennes sorties sous cet identifiant (remplacer `<id>` par la valeur affichée) :
      `docker exec <conteneur> sh -c 'cd /data/output && mkdir -p <id> && mv [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] <id>/'`
      Si elles avaient déjà été rangées sous `adrien/` :
      `docker exec <conteneur> sh -c 'cd /data/output && mkdir -p <id> && mv adrien/* <id>/ && rmdir adrien'`
- [ ] Vérifier une journée migrée :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <une date migrée>`
- [ ] Vérifier l'API depuis son conteneur (le jeton est lu dans l'environnement, pas tapé) :
      `docker exec <conteneur-api> sh -c 'wget -qO- --header "Authorization: Bearer $RSSRESUME_API_TOKEN" http://127.0.0.1:8080/api/v1/profils'`
      puis `…/api/v1/profils/adrien/journees` : les journées migrées doivent y apparaître.

## Après le premier passage

- [ ] Logs : `RSSResume : … profil(s)` puis `Tournée du … : adrien`.
- [ ] **Re-scoring unique attendu** : les tags deviennent `adrien-score-NN`, `adrien-theme-…`,
      `adrien-scoring-…`, `adrien-digested` ; les anciens, sans préfixe, sont ignorés. Les logs
      montrent `scoring : 0 note(s) relue(s) des tags, N à calculer`.
- [ ] Aucune ligne `Échec du digest de « adrien »` ni `identifiant … est aussi celui de` dans les logs.
- [ ] L'email est arrivé ; le bilan se relit :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <AAAA-MM-JJ>`
- [ ] (Facultatif) Supprimer dans FreshRSS les anciens labels sans préfixe (`score-NN`, `theme-…`,
      `scoring-…`, `digested`) : ils ne sont plus ni lus ni écrits.
- [ ] (Facultatif) Une fois le site en service, `/data/profils/` n'est plus lu par personne : le
      garder comme sauvegarde, ou le supprimer.
