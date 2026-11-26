# RSSResume - site d'administration

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
email ne part : chacun, lien de confirmation compris, est écrit dans la console du
serveur. Copier le lien `…/confirmer/<jeton>` dans le navigateur pour activer un compte.

## Vérifications

```bash
npm run check   # svelte-check (types TypeScript et Svelte)
npm run test    # Vitest : logique serveur
npm run build   # build de production dans build/
```

Les tests couvrent la validation (username, mot de passe, email), les sessions (empreinte
en base, expiration, prolongation, refus d'un compte en attente), les comptes (droit
d'administrer réservé aux comptes confirmés, purge à sept jours, confirmation et première
connexion qui ne valent qu'une fois, migration des comptes existants), les jetons de
confirmation (empreinte, 24 h, usage unique, remplacement), l'inscription en deux temps
(profil du métier choisi, texte, axes, catégories, régime, ou « Autre », métier inconnu,
gabarits injoignables ; profil, alerte et bienvenue à la confirmation seulement et une
seule fois, lien expiré, API indisponible, renvoi, fermeture sans transport d'email), la
destination après connexion (le profil la première fois), les destinataires (ajout en
attente, confirmation, retrait immédiat, plafond, fréquence, axes et catégories conservés
quand la page ne les montre pas, enregistrés quand elle les montre, clé retirée quand tout
est coché), les transports d'email et le contenu de la bienvenue, le client d'API contre la
fausse API (dont le champ `id`, jamais renvoyé, les gabarits, les catégories proposées et le
champ d'une erreur de validation), la page « Mon profil » (seules les catégories autorisées
proposées, cochées selon le profil, erreur affichée sous son champ, stack facultative,
régimes expliqués, gabarit pré-rempli), la lecture de son formulaire (axes et leurs slugs,
catégories cochées, aucune refusée), et le relais audio : contrôle propriétaire/admin,
chemins forgés, transmission du `Range` et relais des `206`/`416`.

## Arborescence

```
src/
  env.ts                     variables d'environnement déclarées (SvelteKit 3)
  hooks.server.ts            session → locals.utilisateur, en-têtes de sécurité
  lib/profil.ts              types du profil, régimes, axes, lecture du formulaire (partagé)
  lib/lecteur.svelte.ts      le lecteur audio unique, fourni par le layout : survit aux navigations
  lib/LecteurGlobal.svelte   le mini-lecteur en bas d'écran, quand la page n'a pas d'emplacement
  lib/LecteurPlein.svelte    l'emplacement plein qu'une page offre à une piste
  lib/server/
    contexte.ts              le seul endroit où l'environnement est lu et tout assemblé
    api-resume.ts            client typé de l'API de résumé
    base.ts                  SQLite (node:sqlite) et migrations
    comptes.ts               comptes (en attente / confirmés), Argon2id, droit de consulter
    sessions.ts              sessions par jeton aléatoire
    jetons-email.ts          jetons des liens de confirmation
    inscription.ts           compte en attente (métier choisi), puis profil + alerte + bienvenue
    reinitialisation.ts      mot de passe oublié : lien d'une heure, à usage unique
    identifiants.ts          changement de mot de passe et d'adresse du compte
    destinataires.ts         adresses de réception : confirmées avant d'atteindre l'API
    courrier.ts              emails du site ; transports Resend, console, absent
    relais-audio.ts          contrôle d'accès et relais du MP3 avec Range
    limiteur.ts              limitation des tentatives
    garde.ts, cookie.ts      gardes de pages, cookie de session
  routes/
    inscription, connexion, deconnexion, profil, resumes/[username], admin
    confirmer/[jeton], renvoyer-lien   la vérification d'email
    mot-de-passe-oublie, reinitialiser/[jeton], profil/compte   les identifiants
    confidentialite          page publique : données, durées, sous-traitants, contact
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
- **CSRF** : assuré par SvelteKit, en production, tout `POST` de formulaire dont l'en-tête
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
  - le formulaire fait choisir un **métier** parmi les gabarits de l'API (ou « Autre ») ;
    son texte s'affiche, modifiable. Le compte en attente garde une copie des réglages du
    gabarit (texte, stack, régime, axes, catégories) et le profil est créé avec eux : le premier
    digest correspond déjà au métier. API injoignable à l'affichage : le formulaire revient
    au texte général, sans liste ;
  - à la confirmation, un **email de bienvenue** part une fois : ce que la personne va
    recevoir, l'heure du passage, où ajuster son profil, comment ne plus rien recevoir. Un
    échec d'envoi est journalisé, sans relance ni effet sur le compte ;
  - la **première connexion** mène à « Mon profil » plutôt qu'à une liste de résumés vide.
    Une connexion qui suit un lien vers une autre page (`?suite=`) y mène sans la consommer ;
  - tant que le compte est en attente, la connexion est refusée, et la session aussi. Le
    message n'apparaît qu'après un mot de passe correct. La page « Renvoyer le lien » répond
    la même chose quelle que soit l'adresse (3 demandes par adresse et 10 par IP et par heure) ;
  - un compte jamais confirmé est supprimé après 7 jours, au démarrage et à chaque
    inscription : son adresse et son username sont alors libérés ;
  - sans `RESEND_API_KEY` ou `MAIL_FROM` en production, les inscriptions sont refusées
    (« inscriptions momentanément fermées ») et l'erreur est journalisée.
- **Mot de passe oublié** : la page répond la même chose quelle que soit l'adresse, et
  l'email part sans être attendu (le temps de réponse ne trahit rien) ; seul un compte
  confirmé reçoit un lien. Lien d'une heure, à usage unique, caduc si l'adresse du compte a
  changé ; l'ouvrir ne consomme rien. Le nouveau mot de passe ferme toutes les sessions,
  révoque les liens de réinitialisation et d'adresse en cours et lève le blocage de
  connexion de l'adresse. 10 demandes par IP et par heure (429) ; au-delà de 3 par adresse,
  la réponse reste la même mais rien ne part.
- **Mon compte** (`/profil/compte`) : changer de mot de passe ou d'adresse exige le mot de
  passe actuel (échecs comptés avec ceux de la connexion). Le nouveau mot de passe ferme les
  autres sessions ; la nouvelle adresse ne s'applique qu'au clic sur le lien qu'elle reçoit,
  et l'ancienne en est prévenue. Seul le dernier lien d'adresse demandé vaut, et aucun ne
  survit à une confirmation. Les destinataires du digest, eux, restent ceux du profil.
- **Confidentialité** (`/confidentialite`, sans connexion, lien en pied de page) : l'adresse
  publiée est `CONTACT_EMAIL`, à défaut `ADMIN_EMAIL`.
- **Mon profil** : le texte de veille avec une aide en trois rubriques (mon métier, ce que je
  veux suivre, ce qui ne m'intéresse pas) et le texte d'un gabarit en exemple ; « Repartir
  d'un gabarit », qui pré-remplit sans rien enregistrer ; les catégories à cocher, celles que
  l'API autorise et elles seules, avec leur description, tout coché, la personne suit aussi
  les catégories ajoutées plus tard ; le régime de sécurité expliqué en une ligne par valeur ;
  les rubriques (axes), de 3 à 6, vides pour celles par défaut ; la stack, facultative. Un
  refus de l'API s'affiche sous le champ qu'elle nomme.
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
  docker exec <conteneur-du-site> node -e "const {DatabaseSync}=require('node:sqlite'); \
    new DatabaseSync('/data-web/comptes.sqlite').prepare(\"UPDATE comptes SET role='admin' WHERE username=?\").run('son-username')"
  ```

## Déploiement (Dokploy)

Le site est une **application Dokploy distincte** du compose de l'appli de résumé : il se
déploie, redémarre et se met à jour sans toucher au travailleur du matin. Il appelle l'API
de résumé, le service `api` du compose (même image que `rssresume`, lancée par
`python -m rssresume.api`, port 8080 jamais publié), par l'alias `rssresume-api` que ce
service porte sur `dokploy-network`, le réseau commun à toutes les applications Dokploy.

Dans Dokploy, une application de type **Application** :

1. **Source** : le dépôt, branche `main` ; **Build Type** `Dockerfile`, **Docker File**
   `Dockerfile`, **Docker Context Path** `web` (le contexte est le dossier `web/`, pas la
   racine) ; **Watch Paths** `web/**`, tout ce que l'image emporte est dans le contexte ;
2. onglet **Environment** :
   - `RSSRESUME_API_URL=http://rssresume-api:8080`
   - `RSSRESUME_API_TOKEN` : le même que celui du compose de l'appli de résumé
   - `ADMIN_EMAIL`, `RESEND_API_KEY`, `MAIL_FROM` (domaine vérifié chez Resend)
   - `CONTACT_EMAIL` (facultative) : le contact de la page de confidentialité ; à défaut,
     `ADMIN_EMAIL` y est publiée
   - `ORIGIN=https://<le domaine du site>`
   - `ADDRESS_HEADER=X-Forwarded-For` et `XFF_DEPTH=1` (derrière Traefik : l'IP du client
     pour la limitation des tentatives)
3. onglet **Advanced → Volumes** : un volume monté sur `/data-web` (la base des comptes ;
   sans lui, chaque redéploiement efface les comptes) ;
4. onglet **Domains** : le domaine du site, port `3000`, HTTPS (Let's Encrypt) ;
5. déployer, créer le compte de `ADMIN_EMAIL` par la page d'inscription, puis le
   confirmer par le lien reçu.

Le port 8080 de l'API n'est publié nulle part : seules les applications de
`dokploy-network` l'atteignent, et le jeton reste exigé.

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
