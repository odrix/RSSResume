# Déployer les profils multiples sur Dokploy

Actions manuelles, dans l'ordre. Cocher au fur et à mesure, vider le fichier une fois fait.
`<conteneur>` : le nom du conteneur `rssresume` (`docker ps --format '{{.Names}}' | grep rssresume`).

## Avant de redéployer (conteneur actuel encore en marche)

- [ ] Créer le dossier des profils dans le volume :
      `docker exec -u root <conteneur> sh -c 'mkdir -p /data/profils && chown rssresume:rssresume /data/profils'`
- [ ] Copier le document de profil actuel sous son nom (`adrien`) — depuis la machine qui l'a,
      après l'avoir posé sur le VPS (`scp input/moi/profile.json vps:/tmp/adrien.json`). Il doit
      être un objet JSON (`{"profil": "…", …}`), pas du texte brut :
      `docker cp /tmp/adrien.json <conteneur>:/data/profils/adrien.json`
      `docker exec -u root <conteneur> chown rssresume:rssresume /data/profils/adrien.json`
      (le propriétaire compte : le premier passage écrit l'`id` dans le fichier).

## Onglet Environment

- [ ] Retirer `RSSRESUME_PROFILE_FILE` (posée avec le dossier, elle fait échouer le lancement).
- [ ] Retirer `RSSRESUME_PROFILE` si elle y est (elle n'est plus lue et fait échouer le lancement).
- [ ] Ne rien ajouter : `RSSRESUME_PROFILES_DIR=/data/profils` est imposée par `docker-compose.yml`.
- [ ] Retirer le montage `./input/moi:/config:ro` s'il avait été ajouté au compose.

## Juste après le redéploiement (avant le premier passage)

- [ ] Logs au démarrage : `RSSResume : 1 profil(s) : adrien`. Une erreur `RSSRESUME_PROFILES_DIR … n'existe pas`
      ou `… sont posées ensemble` renvoie aux étapes ci-dessus.
- [ ] Donner son identifiant au profil (généré, écrit dans le fichier, et affiché) :
      `docker exec <conteneur> python -c "from rssresume.profil import charger_profil; print(charger_profil('/data/profils', 'adrien').id)"`
- [ ] Ranger les anciennes sorties sous cet identifiant (remplacer `<id>` par la valeur affichée) :
      `docker exec <conteneur> sh -c 'cd /data/output && mkdir -p <id> && mv [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] <id>/'`
      Si elles avaient déjà été rangées sous `adrien/` :
      `docker exec <conteneur> sh -c 'cd /data/output && mkdir -p <id> && mv adrien/* <id>/ && rmdir adrien'`
- [ ] Vérifier une journée migrée :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <une date migrée>`

## Après le premier passage

- [ ] **Re-scoring unique attendu** : les tags deviennent `adrien-score-NN`, `adrien-theme-…`,
      `adrien-scoring-…`, `adrien-digested` ; les anciens, sans préfixe, sont ignorés. Les logs
      montrent `scoring : 0 note(s) relue(s) des tags, N à calculer`.
- [ ] Aucune ligne `Échec du digest de « adrien »` ni `identifiant … est aussi celui de` dans les logs.
- [ ] L'email est arrivé ; le bilan se relit :
      `docker exec <conteneur> python -m rssresume --journal --profil adrien --date <AAAA-MM-JJ>`
- [ ] (Facultatif) Supprimer dans FreshRSS les anciens labels sans préfixe (`score-NN`, `theme-…`,
      `scoring-…`, `digested`) : ils ne sont plus ni lus ni écrits.
