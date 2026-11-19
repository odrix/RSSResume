# RSSResume — site d'administration

Le site où chacun crée son compte, écrit son profil de veille et écoute ses résumés audio.
L'administrateur y voit tous les profils et peut écouter les résumés de chacun.

Deux applications, deux bases :

- **l'appli de résumé** (Python, à la racine du dépôt) possède les profils et les journées,
  et les expose par une API HTTP dont le contrat est dans [API.md](API.md) ;
- **ce site** (SvelteKit, Svelte 5, TypeScript, adapter-node) possède les comptes et les
  sessions, dans sa propre base SQLite. Il appelle l'API depuis son serveur seulement : le
  jeton `RSSRESUME_API_TOKEN` n'atteint jamais le navigateur.

## Développement

Node ≥ 22.17 (l'image utilise Node 24).

```bash
cd web
npm install
cp .env.example .env.local   # puis RSSRESUME_API_URL=http://localhost:8080
npm run mock                 # fausse API sur http://localhost:8080 (jeton « dev »)
npm run dev                  # dans un autre terminal : http://localhost:5173
```

La fausse API ([mock/faux-api.js](mock/faux-api.js)) tient le contrat en mémoire et donne
à chaque profil créé deux journées d'audio silencieux, de quoi essayer le lecteur et l'avance
dans le fichier. Un redémarrage la vide ; les comptes, eux, restent dans `data/comptes.sqlite`.

Sans `RESEND_API_KEY` et hors production (`NODE_ENV` différent de `production`), aucun
email ne part : chacun — lien de confirmation compris — est écrit dans la console du
serveur. Copier le lien `…/confirmer/<jeton>` dans le navigateur pour activer un compte.

## Vérifications

```bash
npm run check   # svelte-check (types TypeScript et Svelte)
npm run test    # Vitest : logique serveur
npm run build   # build de production dans build/
```

Les tests couvrent la validation (username, mot de passe, email), les sessions (empreinte
en base, expiration, prolongation, refus d'un compte en attente), les comptes (droit
d'administrer réservé aux comptes confirmés, purge à sept jours), les jetons de
confirmation (empreinte, 24 h, usage unique, remplacement), l'inscription en deux temps
(profil et alerte à la confirmation seulement, lien expiré, API indisponible, renvoi,
fermeture sans transport d'email), les destinataires (ajout en attente, confirmation,
retrait immédiat, plafond, fréquence), les transports d'email, le client d'API contre la
fausse API (dont le champ `id`, jamais renvoyé), et le relais audio : contrôle
propriétaire/admin, chemins forgés, transmission du `Range` et relais des `206`/`416`.

## Arborescence

```
src/
  env.ts                     variables d'environnement déclarées (SvelteKit 3)
  hooks.server.ts            session → locals.utilisateur, en-têtes de sécurité
  lib/profil.ts              types du profil, lecture du formulaire (partagé)
  lib/server/
    contexte.ts              le seul endroit où l'environnement est lu et tout assemblé
    api-resume.ts            client typé de l'API de résumé
    base.ts                  SQLite (node:sqlite) et migrations
    comptes.ts               comptes (en attente / confirmés), Argon2id, droit de consulter
    sessions.ts              sessions par jeton aléatoire
    jetons-email.ts          jetons des liens de confirmation
    inscription.ts           compte en attente, puis profil + alerte à la confirmation
    destinataires.ts         adresses de réception : confirmées avant d'atteindre l'API
    courrier.ts              emails du site ; transports Resend, console, absent
    relais-audio.ts          contrôle d'accès et relais du MP3 avec Range
    limiteur.ts              limitation des tentatives
    garde.ts, cookie.ts      gardes de pages, cookie de session
  routes/
    inscription, connexion, deconnexion, profil, resumes/[username], admin
    confirmer/[jeton], renvoyer-lien   la vérification d'email
    audio/[username]/[date]/[nom]   le relais audio (GET)
mock/                        fausse API (tests et développement)
```

## Dépendances

Une seule dépendance d'exécution, le reste ne sert qu'à construire :

| Paquet | Version | Pourquoi |
| --- | --- | --- |
| `@node-rs/argon2` | 2.2.2 | Argon2id, le hachage de mot de passe recommandé par l'OWASP. Binaires précompilés (dont musl pour alpine) : rien à compiler dans l'image. `node:crypto` n'offre Argon2 qu'en expérimental. |
| `@sveltejs/kit` | 3.4.0 | Le framework. La 3 et non la 2 : les correctifs de sécurité de 2026 (redirection ouverte via les formulaires améliorés, `cookie` < 0.7) n'existent que sur la branche 3. |
| `@sveltejs/adapter-node` | 6.0.5 | Serveur Node autonome, pour Docker. |
| `svelte`, `@sveltejs/vite-plugin-svelte`, `vite` | 5.58.0, 7.3.1, 8.3.8 | Exigés par SvelteKit 3. |
| `typescript`, `svelte-check`, `@types/node` | 6.0.3, 4.7.8, 24.19.2 | Vérification des types (`npm run check`). |
| `vitest` | 5.1.1 | Tests. |

Ce qui n'est **pas** là, volontairement :

- **pas de pilote SQLite tiers** (better-sqlite3) : `node:sqlite` est intégré à Node depuis
  22.13, synchrone, et évite un module natif à reconstruire. Il affiche un avertissement
  « experimental », coupé par `--disable-warning=ExperimentalWarning` ;
- **pas de Lucia** (déprécié) ni de bibliothèque de sessions : une table, un jeton aléatoire
  de 256 bits, son empreinte SHA-256 en base ([sessions.ts](src/lib/server/sessions.ts)) ;
- **pas de SDK Resend** : un seul `POST` par `fetch` ([courrier.ts](src/lib/server/courrier.ts)) ;
- **pas de framework CSS** : une feuille de style sobre, thème sombre suivi du système.

## Sécurité

- **Mots de passe** : 12 caractères minimum (256 maximum), Argon2id (19 Mio, 2 passes).
  Une adresse inconnue est vérifiée contre une empreinte leurre : la réponse prend le même
  temps et dit la même chose (« Adresse ou mot de passe incorrect »).
- **Sessions** : cookie `session` en `HttpOnly`, `Secure`, `SameSite=Lax`, 30 jours,
  prolongé quand il reste moins de 15 jours. Seule l'empreinte du jeton est en base.
  Déconnexion par `POST` seulement.
- **CSRF** : assuré par SvelteKit — en production, tout `POST` de formulaire dont l'en-tête
  `Origin` n'est pas celui du site est refusé (403). SvelteKit 3 ne permet plus de le
  désactiver ; il faut en revanche que **`ORIGIN`** soit la vraie adresse publique.
  Vérifié à la main : un `POST /connexion` avec `Origin: http://evil.example` → 403.
- **Vérification d'email** :
  - un compte naît **en attente**. Le lien envoyé porte un jeton de 256 bits ; seule son
    empreinte SHA-256 est en base. Il est valable 24 h, ne sert qu'une fois, et un nouveau
    lien annule le précédent ;
  - ouvrir le lien n'affiche qu'une page avec un bouton : la confirmation est un `POST`,
    pour qu'un antivirus de messagerie qui suit les liens ne la déclenche pas ;
  - le **profil n'est créé côté API qu'à la confirmation** : aucun digest ne part vers une
    adresse non prouvée. L'alerte à `ADMIN_EMAIL` part à ce moment-là aussi ;
  - tant que le compte est en attente, la connexion est refusée, et la session aussi. Le
    message n'apparaît qu'après un mot de passe correct. La page « Renvoyer le lien » répond
    la même chose quelle que soit l'adresse (3 demandes par adresse et 10 par IP et par heure) ;
  - un compte jamais confirmé est supprimé après 7 jours, au démarrage et à chaque
    inscription : son adresse et son username sont alors libérés ;
  - sans `RESEND_API_KEY` ou `MAIL_FROM` en production, les inscriptions sont refusées
    (« inscriptions momentanément fermées ») et l'erreur est journalisée.
- **Destinataires du digest** : dans « Mon profil », une adresse ajoutée reçoit son propre
  lien et attend dans la base du site. L'API ne reçoit que les adresses confirmées. L'adresse
  du compte, prouvée à l'inscription, passe directement. Retirer une adresse est immédiat.
  Au plus 10 adresses en attente, et 10 liens par compte et par heure.
- **Limitation** : 5 échecs de connexion par adresse et 30 par IP sur 15 minutes ;
  5 inscriptions par IP et par heure. En mémoire (un seul processus).
- **Accès aux résumés** : le propriétaire ou l'administrateur. Les autres reçoivent un 404,
  pas un 403, pour ne pas confirmer qu'un username existe. La route audio valide date et nom
  de fichier avant d'appeler l'API.
- **Redirections** : le paramètre `suite` de la connexion n'est suivi que s'il reste sur le site.
- **En-têtes** : CSP stricte (scripts par nonce, aucune origine tierce), `X-Frame-Options:
  DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- **Administrateur** : un compte **confirmé** dont l'email est `ADMIN_EMAIL`, ou un compte
  confirmé de rôle `admin` en base. S'inscrire avec l'adresse de l'administrateur ne suffit
  donc pas : il faut aussi ouvrir le lien reçu dans sa boîte. Pour donner le rôle à un autre
  compte :

  ```bash
  docker compose exec web node -e "const {DatabaseSync}=require('node:sqlite'); \
    new DatabaseSync('/data-web/comptes.sqlite').prepare(\"UPDATE comptes SET role='admin' WHERE username=?\").run('son-username')"
  ```

## Déploiement (Dokploy)

Le site est un service de plus dans le `docker-compose.yml` de la racine. Il appelle l'API
de résumé, qui tourne dans son propre service `api` (même image que `rssresume`, lancée par
`python -m rssresume.api`, port 8080 interne), par son nom sur le réseau du projet. Bloc à
ajouter sous `services:` :

```yaml
  web:
    build: ./web
    restart: unless-stopped
    env_file:
      - path: .env
        required: false
    environment:
      RSSRESUME_API_URL: http://api:8080
      DATABASE_PATH: /data-web/comptes.sqlite
      PORT: "3000"
      # Derrière Traefik : l'IP du client pour la limitation des tentatives.
      ADDRESS_HEADER: X-Forwarded-For
      XFF_DEPTH: "1"
    expose:
      - "3000"
    volumes:
      - web-data:/data-web
    depends_on:
      - api
```

et sous `volumes:` :

```yaml
  web-data:
```

Les services partagent le réseau par défaut du projet compose ; rien d'autre à déclarer.
Le port 8080 du service `api` n'est publié nulle part : seul le site l'atteint.

Dans Dokploy :

1. onglet **Environment** : `RSSRESUME_API_TOKEN` (le même que celui de l'API),
   `ADMIN_EMAIL`, `RESEND_API_KEY`, `MAIL_FROM` (domaine vérifié chez Resend), et
   `ORIGIN=https://<le domaine du site>` ;
2. onglet **Domains** : un domaine sur le service `web`, port `3000`, HTTPS (Let's Encrypt) ;
3. déployer, créer le compte de `ADMIN_EMAIL` par la page d'inscription, puis le
   confirmer par le lien reçu.

`RESEND_API_KEY` et `MAIL_FROM` sont **indispensables en production** : sans elles,
l'image (`NODE_ENV=production`) refuse les inscriptions, puisque aucun lien de
confirmation ne pourrait partir.

Construire et lancer l'image seule :

```bash
docker build -t rssresume-web web
docker run --rm -p 3000:3000 -v rssresume-web:/data-web \
  -e ORIGIN=http://localhost:3000 -e RSSRESUME_API_URL=http://host.docker.internal:8080 \
  -e RSSRESUME_API_TOKEN=dev rssresume-web
```
