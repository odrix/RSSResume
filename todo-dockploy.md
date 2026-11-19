# Déployer les profils multiples sur Dokploy

Actions manuelles, dans l'ordre. Cocher au fur et à mesure, vider le fichier une fois fait.
`<conteneur>` : le nom du conteneur `rssresume` (`docker ps --format '{{.Names}}' | grep rssresume`).

## Avant de redéployer (conteneur actuel encore en marche)

- [ ] Créer le dossier des profils dans le volume :
      `docker exec -u root <conteneur> sh -c 'mkdir -p /data/profils && chown rssresume:rssresume /data/profils'`
- [ ] Copier le document de profil actuel sous son nom (`adrien`) — depuis la machine qui l'a,
      après l'avoir posé sur le VPS (`scp input/moi/profile.json vps:/tmp/adrien.json`) :
      `docker cp /tmp/adrien.json <conteneur>:/data/profils/adrien.json`
      `docker exec -u root <conteneur> chown rssresume:rssresume /data/profils/adrien.json`
- [ ] Ranger les anciennes sorties sous le nom du profil :
      `docker exec <conteneur> sh -c 'cd /data/output && mkdir -p adrien && mv [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] adrien/'`

## Onglet Environment

- [ ] Retirer `RSSRESUME_PROFILE_FILE` (posée avec le dossier, elle fait échouer le lancement).
- [ ] Retirer `RSSRESUME_PROFILE` si elle y est (elle n'est plus lue et fait échouer le lancement).
- [ ] Ne rien ajouter : `RSSRESUME_PROFILES_DIR=/data/profils` est imposée par `docker-compose.yml`.
- [ ] Retirer le montage `./input/moi:/config:ro` s'il avait été ajouté au compose.

## Après le redéploiement

- [ ] Logs au démarrage : `RSSResume : 1 profil(s) : adrien`. Une erreur `RSSRESUME_PROFILES_DIR … n'existe pas`
      ou `… sont posées ensemble` renvoie aux étapes ci-dessus.
- [ ] Premier passage : **re-scoring unique attendu**. Les tags deviennent `adrien-score-NN`,
      `adrien-theme-…`, `adrien-scoring-…`, `adrien-digested` ; les anciens, sans préfixe, sont
      ignorés. Les logs montrent `scoring : 0 note(s) relue(s) des tags, N à calculer`.
- [ ] Vérifier le bilan du premier passage :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <AAAA-MM-JJ>`
- [ ] Vérifier que l'email est arrivé, et qu'aucune ligne `Échec du digest de « adrien »` n'est dans les logs.
- [ ] Vérifier le renvoi d'une ancienne journée migrée :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <une date migrée>`
- [ ] (Facultatif) Supprimer dans FreshRSS les anciens labels sans préfixe (`score-NN`, `theme-…`,
      `scoring-…`, `digested`) : ils ne sont plus ni lus ni écrits.
