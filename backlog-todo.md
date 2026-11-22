# Backlog — à faire

Le seul backlog du dépôt. Les items traités partent dans [backlog-done.md](backlog-done.md),
avec leur date de réalisation ; `/backlog-pop` les traite (voir
[la skill](.claude/skills/backlog-pop/SKILL.md)).

Repris le 2026-11-21 de `totorss.md` (les numéros d'item y sont conservés : BL-020 est
l'item 20) et de `todo-improve.md`. Les actions de déploiement ponctuelles restent dans
`todo-dockploy.md`, gitignoré : ce sont des gestes sur une instance, pas des évolutions.

BL-037 à BL-053 viennent de l'étude d'ouverture du 2026-11-22 : servir des personnes hors
TransfertPro (CTO, dev, DSI, RSSI, chef de projet, QA, PO/PM, designer). Décisions prises :
catégories FreshRSS regroupées par thématique métier, plus des catégories privées (veille
concurrentielle, à développer plus tard) ; axes de veille portés par des gabarits métier ;
régime CVE réglé dans le profil ; inscriptions ouvertes, sans validation.

## Règles

- **Identifiant** `BL-NNN`, jamais réattribué. Prochain libre : **BL-065**.
- **Priorité** de 1 (la plus urgente) à 5. `/backlog-pop` prend la plus petite, puis
  l'identifiant le plus bas à priorité égale.
- **Catégorie** = la zone du code touchée. Deux items de catégories différentes peuvent se
  traiter en parallèle sans se marcher dessus :

  | Catégorie | Zone |
  | --- | --- |
  | `pipeline` | `digest.py`, sélection, scoring, `models.py`, `config.py` |
  | `prompts` | `llm/prompts.py`, `llm/providers.json` |
  | `freshrss` | `external/freshrss*`, tags et libellés |
  | `cli` | `cli.py` et ses options |
  | `web` | `web/`, `rssresume/api` |
  | `docs` | README, FONCTIONNEMENT, `docs/`, études |
  | `outillage` | `.claude/`, `.github/`, `tests/support.py` |
  | `exploitation` | hors dépôt (serveur, FreshRSS) : jamais traité en automatique |

- **Dépend de** (facultatif) : un item n'est pas pris tant que ses dépendances sont ici.
- **Tests d'acceptation** : ce qui doit être vrai, et testé dans `tests/` quand c'est du code,
  pour que l'item parte dans `backlog-done.md`.

---

### BL-037 — Catalogue des catégories : publiques par métier, privées par propriétaire

- **Catégorie** : pipeline
- **Priorité** : 1
- **Description** : aujourd'hui chaque profil reçoit toutes les catégories du FreshRSS partagé, y
  compris la veille concurrentielle TransfertPro (alertes Google, « Veille marché ») — et l'email
  en affiche les sources et les articles « à surveiller ». Décrire chaque catégorie dans un fichier
  de données hors du code, à la manière de `llm/providers.json` : libellé FreshRSS, description
  lisible, métiers concernés, et visibilité — `publique`, ou `privee` avec ses propriétaires
  (`username`). Une catégorie privée n'est jamais servie, notée, résumée ni montrée à un autre
  profil. Une catégorie absente du catalogue n'est servie à personne : une nouvelle catégorie
  FreshRSS ne doit pas apparaître chez tout le monde parce que quelqu'un l'a créée. Plan à faire
  valider (articulation avec `RSSRESUME_CATEGORIES`, `RSSRESUME_CERTFR_CATEGORIES`, la tournée qui
  lit une seule fois).
- **Bénéfice attendu** : le prérequis de l'ouverture — rien de la veille TransfertPro ne fuit vers
  un externe, et le site peut présenter les catégories à choisir.
- **Tests d'acceptation** :
  - [ ] le fichier est validé au chargement ; une entrée fautive lève au lancement ;
  - [ ] une catégorie privée n'atteint ni le scoring, ni le résumé, ni l'email d'un non-propriétaire ;
  - [ ] une catégorie FreshRSS absente du catalogue n'est servie à personne, et le log le dit ;
  - [ ] le marquage comme lu de la tournée reste inchangé ;
  - [ ] README et FONCTIONNEMENT décrivent le fichier.

### BL-038 — Abonnement de chaque profil à ses catégories

- **Catégorie** : pipeline
- **Priorité** : 1
- **Dépend de** : BL-037
- **Description** : nouvelle clé `categories` du document de profil (`profil.py`), la liste des
  catégories publiques suivies, plus les privées dont la personne est propriétaire. Le filtre
  s'applique **avant** le scoring, dans `AppConfig.pour` ou la tournée : une catégorie non suivie ne
  coûte rien à ce profil. Une catégorie CERT-FR n'est servie qu'à qui la suit — fini le « 7 avis
  CERT-FR, aucun sur votre stack » quotidien chez un designer. Clé absente : comportement actuel
  restreint aux catégories que le catalogue autorise (les profils existants ne perdent rien).
  `profil_depuis_dict` valide la clé, donc l'API la refuse comme la tournée.
- **Bénéfice attendu** : c'est le premier levier de pré-filtrage par public et le plus gros gain de
  coût — une personne ne note plus que ce qu'elle suit.
- **Tests d'acceptation** :
  - [ ] un profil abonné à A et B ne fait noter ni résumer aucun article de C ;
  - [ ] une catégorie inconnue ou privée d'un autre est refusée à la validation, avec un message clair ;
  - [ ] clé absente : comportement inchangé dans le périmètre du catalogue ;
  - [ ] l'API normalise et relit la clé (tests `api`) ;
  - [ ] FONCTIONNEMENT (« Le document de la personne ») documente la clé.

### BL-043 — Compte : mot de passe oublié, suppression, confidentialité

- **Catégorie** : web
- **Priorité** : 3
- **Description** : avec des inscriptions ouvertes, le site doit tenir seul face à des inconnus. Il
  manque : « mot de passe oublié » (lien à usage unique, sur la mécanique de `jetons-email.ts`),
  changement de mot de passe et d'adresse du compte, **suppression du compte** par la personne
  (compte, profil via le `DELETE` de l'API déjà au contrat, et sorties `output/<id>/`), et une page
  de confidentialité : données conservées (email, profil, stack, journées), finalité, durée,
  sous-traitants (fournisseur LLM, Resend), contact. Lien dans le pied du site.
- **Bénéfice attendu** : ouvrir sans dette RGPD et sans tickets « je ne peux plus me connecter ».
- **Tests d'acceptation** :
  - [ ] la réinitialisation ne révèle pas si une adresse a un compte, et le lien expire ;
  - [ ] la suppression retire compte, profil et sorties, et la tournée suivante ne sert plus personne
        sous ce nom ;
  - [ ] la page de confidentialité est accessible sans connexion ;
  - [ ] `npm run check` et `npm test` verts, tests API en unittest pour la suppression des sorties.

### BL-044 — Email quotidien prêt pour des lecteurs extérieurs

- **Catégorie** : pipeline (`newsletter.py`), web pour la page de désabonnement
- **Priorité** : 1
- **Description** : la `Lettre` n'a ni lien vers le site, ni désabonnement, ni identité
  (`NOTE_PIED` vide), et l'audio part en pièce jointe — lourd, souvent filtré, plafonné à 25 Mo
  chez Gmail. Ajouter au pied : qui envoie, pourquoi on reçoit ce message, lien « mes résumés »,
  lien « modifier mon profil », lien de désabonnement signé (sans connexion) ; poser les en-têtes
  `List-Unsubscribe` et `List-Unsubscribe-Post` (désabonnement en un clic, exigé par Gmail et Yahoo
  pour les expéditeurs en volume). Proposer l'audio en lien vers le site plutôt qu'en pièce jointe
  (réglage de l'installation). Écrire en toutes lettres la date de la lettre « aucun article »,
  aujourd'hui en ISO. `--send-only` doit produire la même lettre.
- **Bénéfice attendu** : une lettre qu'un inconnu reconnaît, peut régler et peut arrêter — et qui
  ne finit pas dans les indésirables.
- **Tests d'acceptation** :
  - [ ] le pied et les en-têtes sont présents dans les versions HTML et texte ;
  - [ ] le lien de désabonnement vide les destinataires du profil, sans session, et ne sert qu'une fois ;
  - [ ] l'audio en lien ne joint plus le mp3 et pointe vers la route audio authentifiée du site ;
  - [ ] la lettre « aucun article » porte une date en toutes lettres ;
  - [ ] `--send-only` rend la même lettre que le passage du jour.

### BL-052 — Étudier le coût et le passage à l'échelle avec des inscriptions ouvertes

- **Catégorie** : docs
- **Priorité** : 1
- **Description** : étude, sans code. Chaque profil note tous les articles de ses catégories, et se
  fait résumer les siens : la facture croît en profils × articles, et l'inscription est ouverte.
  Chaque profil pose aussi une quinzaine de libellés dans le FreshRSS partagé (`score-NN`,
  `theme-*`, `scoring-<hash>`) : à trente personnes, la barre latérale devient inutilisable. À
  chiffrer à partir des journaux (`runlog`, `pricing`) : coût par profil et par jour, avant et après
  BL-038. Options à comparer : un plafond de profils servis ou un quota, un scoring mutualisé par
  gabarit (une note par gabarit et par article, et non par personne), un cache de scoring sorti des
  libellés FreshRSS vers la base SQLite. Recommandation, avec le seuil de profils où chaque option
  devient nécessaire.
- **Bénéfice attendu** : savoir combien coûte un inscrit avant qu'ils soient cinquante.
- **Tests d'acceptation** :
  - [ ] un document court dans `docs/` : coût mesuré, options, recommandation, seuils de bascule ;
  - [ ] les items de code qui en découlent sont ajoutés à ce backlog.

### BL-022 — Exclure du pipeline les flux non résumables

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : NoLimitSecu est un podcast sans transcription dans son RSS, « FreshRSS
  releases » un changelog : les envoyer au scoring coûte des tokens pour un résultat vide. Ajouter
  une liste d'exclusion **par flux** (pas par catégorie), appariée sur `Article.feed_title`,
  insensible à la casse. Les articles exclus ne sont ni notés ni résumés, mais restent marqués lus
  normalement. Le réglage est personnel : il se déclare dans le document de profil (`profil.py`),
  pas dans l'environnement. Cible initiale : NoLimitSecu et FreshRSS releases.
- **Bénéfice attendu** : moins de tokens de scoring chaque jour, sur des articles qui ne pouvaient
  rien donner.
- **Tests d'acceptation** :
  - [ ] un article d'un flux exclu n'atteint ni le scoring ni le résumé ;
  - [ ] il est quand même marqué lu ;
  - [ ] l'appariement ignore la casse et porte sur le titre du flux, pas sur la catégorie ;
  - [ ] liste absente ou vide : comportement inchangé ;
  - [ ] README et FONCTIONNEMENT documentent la clé du profil.

### BL-024 — Restreindre une exécution : `--categories` et `--limit`

- **Catégorie** : cli
- **Priorité** : 2
- **Description** : mettre au point un prompt oblige à traiter toutes les catégories, donc à
  attendre et à payer pour toutes alors qu'on en teste une. Ajouter `--categories` (liste séparée
  par des virgules, qui surcharge `RSSRESUME_CATEGORIES`) et `--limit N` (plafond d'articles par
  catégorie). `--send-only` et `--journal` couvrent la relecture sans repayer, pas ce besoin.
- **Bénéfice attendu** : une boucle de mise au point de prompt courte et bon marché, qui rend tous
  les autres items moins chers à essayer.
- **Tests d'acceptation** :
  - [ ] `--categories a,b` ne traite que ces deux catégories ;
  - [ ] une catégorie inconnue est signalée clairement, pas ignorée en silence ;
  - [ ] `--limit 3` ne note et ne résume pas plus de 3 articles par catégorie ;
  - [ ] sans les options, comportement inchangé ;
  - [ ] le README les documente dans la section de mise au point du prompt de scoring.

### BL-035 — Jeu d'évaluation des prompts

- **Catégorie** : outillage
- **Priorité** : 2
- **Description** : modifier un prompt de scoring ou de résumé se juge aujourd'hui à l'oreille, sur
  la journée du lendemain. Constituer dans `tests/eval/` un jeu de référence de 30 à 50 articles
  réels, chacun avec une fourchette de note attendue et un verdict « doit / ne doit pas figurer »,
  et une commande (`python -m rssresume.eval` ou option CLI) qui les note avec le prompt courant et
  rend un score : notes hors fourchette, faux positifs, faux négatifs, coût. Les appels réels au
  modèle restent hors de la suite unittest, qui ne teste que la mécanique avec une doublure.
- **Bénéfice attendu** : comparer deux versions d'un prompt sur un chiffre, et laisser Claude
  itérer seul sur un prompt en mesurant chaque essai.
- **Tests d'acceptation** :
  - [ ] le format du jeu de référence est documenté et validé au chargement ;
  - [ ] avec une doublure LLM, le score calculé est exact sur un jeu de 3 articles ;
  - [ ] la commande affiche le coût de l'évaluation, lu de `runlog`/`pricing` ;
  - [ ] aucun article du jeu ne contient de donnée personnelle (`input/` reste la seule source).

### BL-020 — Installer af_readability sur les flux tronqués

- **Catégorie** : exploitation
- **Priorité** : 3
- **Dépend de** : BL-021
- **Description** : sur Next.ink gratuit et les alertes Google, `content_text` est un chapô de 200
  caractères : le résumé résume un résumé. Installer l'extension FreshRSS
  `Niehztog/freshrss-af-readability` et l'activer **uniquement** sur ces flux (Next.ink et les
  onze alertes Google) : activée globalement, ses requêtes en série sans délai déclencheraient des
  limitations sur les ~60 flux.
- **Bénéfice attendu** : le seul item qui améliore l'**entrée** ; aucun prompt ne rattrape un
  chapô.
- **Tests d'acceptation** :
  - [ ] l'extension n'est active que sur les flux listés ;
  - [ ] sur quelques articles, `content_text` côté RSSResume porte le texte intégral.

### BL-021 — Durcir af_readability contre la SSRF

- **Catégorie** : exploitation
- **Priorité** : 3
- **Description** : `extractContent()` fait un cURL vers l'URL de l'article avec `FOLLOWLOCATION`,
  sans `CURLOPT_PROTOCOLS` ni filtrage d'adresses privées, et **stocke la réponse comme contenu
  d'article** : un flux hostile s'en sert de canal d'exfiltration. Patch : protocoles limités à
  HTTP/HTTPS (aussi pour les redirections), résolution DNS préalable et rejet des plages privées et
  réservées (127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7), revalidation après
  chaque redirection. Le patch se documente dans un fichier à part, rejouable après une mise à
  jour ; `vendor/` (readability.php, masterminds/html5, league/uri) entre dans le SBOM.
- **Bénéfice attendu** : rend BL-020 déployable. Les deux vont ensemble ou aucun des deux.
- **Tests d'acceptation** :
  - [ ] une URL d'article vers 127.0.0.1, 169.254.169.254 ou une redirection vers l'une d'elles
        est refusée ;
  - [ ] `file://` et `gopher://` sont refusés ;
  - [ ] le patch est consigné dans le dépôt, avec la marche à suivre pour le rejouer.

### BL-039 — Axes de veille déclarés par le profil, à la place des cinq thématiques figées

- **Catégorie** : prompts
- **Priorité** : 2
- **Description** : `SCORING_RULES` et `models.THEMATIQUES` imposent `reglementaire, cyber, marche,
  stack, autre`, la taxonomie d'un CTO d'éditeur. Pour un QA, un PO ou un designer, tout tombe dans
  `autre` et le regroupement à l'écoute ne veut plus rien dire. Nouvelle clé `axes` du document :
  3 à 6 entrées `{slug, libelle, description}`. Le prompt de scoring énumère les axes du profil et la
  thématique rendue est validée contre eux (repli sur le dernier axe, comme `DEFAULT_THEMATIQUE`
  aujourd'hui). Les tags `theme-<slug>` suivent. Clé absente : les cinq thématiques actuelles, donc
  aucun changement pour un profil existant. Les axes entrant dans le prompt, l'empreinte de scoring
  change et la journée est renotée une fois : à dire dans la doc, pas à contourner. La docstring de
  `profil.py` (« changer ce texte et rien d'autre ») est à corriger au passage. Le barème 7-8, dont
  les exemples sont ceux d'un éditeur (« mouvement d'un concurrent direct »), se reformule en
  termes génériques.
- **Bénéfice attendu** : un classement et un ordre d'écoute qui ont du sens pour chaque métier.
- **Tests d'acceptation** :
  - [ ] le prompt de scoring contient les axes du profil, et pas les cinq par défaut quand le profil
        en déclare ;
  - [ ] une thématique hors des axes est rabattue sur le repli ;
  - [ ] le cache relu des tags reconnaît un `theme-<slug>` d'un axe déclaré ;
  - [ ] clé absente : prompt et validation inchangés ;
  - [ ] `slug` validé (forme d'un libellé FreshRSS), 3 à 6 axes, refus clair sinon.

### BL-040 — Régime de sécurité réglé dans le profil

- **Catégorie** : prompts
- **Priorité** : 1
- **Description** : sans stack déclarée, `cve_instruction()` dicte toutes les versions de toutes les
  CVE : le régime le plus détaillé échoit justement à ceux qui n'exploitent rien. Nouvelle clé
  `securite` du document : `exploitant` (le comportement actuel : gradué sur la stack, ou détail
  complet sans stack), `decideur` (une phrase par CVE, sans versions, sauf si le champ `stack`
  apparie le composant), `curieux` (seulement les failles déjà exploitées ou d'ampleur, une phrase,
  le reste se tait ou se fond). Clé absente : `exploitant`. Le choix est fait par le code, comme
  `stack_declaree` aujourd'hui, jamais laissé au modèle.
- **Bénéfice attendu** : un PO ou un designer n'entend plus réciter de plages de versions.
- **Tests d'acceptation** :
  - [ ] chaque valeur produit la consigne attendue dans `digest_user` et `montage_user` ;
  - [ ] clé absente : consigne identique à l'actuelle ;
  - [ ] valeur inconnue refusée par `profil_depuis_dict`.

### BL-041 — Gabarits par métier

- **Catégorie** : pipeline
- **Priorité** : 2
- **Dépend de** : BL-037, BL-038, BL-039, BL-040
- **Description** : un fichier de données hors du code (`personas.json` ou équivalent) qui donne, pour
  chaque métier — CTO, développeur, DSI, RSSI, chef de projet, QA, PO/PM, designer —, un texte de
  profil, ses axes, ses catégories par défaut, son régime de sécurité, et éventuellement un seuil ou
  un nombre de sujets (donc une durée d'audio). Un gabarit **pré-remplit** un document, il n'y reste
  pas lié : la personne modifie ensuite librement. Exposé par l'API pour que le site le propose, et
  validé au chargement par `profil_depuis_dict` (un gabarit doit donner un profil acceptable). Les
  textes s'écrivent sans rien de TransfertPro.
- **Bénéfice attendu** : un profil utile en un clic au lieu d'une page blanche, et le pré-filtrage
  par public sans demander à chacun de connaître le catalogue.
- **Tests d'acceptation** :
  - [ ] chaque gabarit du fichier produit un document que `profil_depuis_dict` accepte ;
  - [ ] ses catégories par défaut existent dans le catalogue et sont publiques ;
  - [ ] l'API rend la liste des gabarits ;
  - [ ] aucun gabarit ne contient de nom propre d'entreprise.

### BL-045 — Inscription : choix du métier et email de bienvenue

- **Catégorie** : web
- **Priorité** : 2
- **Dépend de** : BL-041
- **Description** : le formulaire pré-remplit aujourd'hui le profil avec `PROFIL_PAR_DEFAUT`
  (`web/src/lib/profil.ts`), axe cyber en tête, et rien n'accompagne la personne après la
  confirmation : son digest part le lendemain avec ce défaut. Remplacer la zone de texte par le choix
  d'un métier (un gabarit), le texte restant visible et modifiable. À la confirmation, envoyer un email
  de bienvenue : ce que la personne va recevoir, à quelle heure, comment ajuster son profil et ses
  catégories, comment se désabonner. Première connexion : arrivée sur le profil, pas sur une liste
  vide.
- **Bénéfice attendu** : le premier digest correspond déjà au métier de la personne.
- **Tests d'acceptation** :
  - [ ] le profil créé à la confirmation reprend le gabarit choisi (texte, axes, catégories, régime) ;
  - [ ] l'email de bienvenue part une fois, à la confirmation ;
  - [ ] la première connexion mène au profil ;
  - [ ] `npm run check` et `npm test` verts.

### BL-046 — Page profil guidée

- **Catégorie** : web
- **Priorité** : 2
- **Dépend de** : BL-038, BL-041
- **Description** : la page n'offre qu'un texte libre sans exemple, et la stack se présente par
  « CERT-FR » et « ex. Keycloak / RH-SSO ». Ajouter : les catégories du catalogue à cocher, avec leur
  description ; les axes modifiables ; le régime de sécurité expliqué en une ligne par valeur ; une
  aide structurée pour le texte (mon métier, ce que je veux suivre, ce qui ne m'intéresse pas) avec
  l'exemple du gabarit ; « repartir d'un gabarit » ; une stack présentée comme facultative
  (« si vous exploitez des serveurs ou des logiciels ») avec des exemples neutres.
- **Bénéfice attendu** : chacun règle son digest sans connaître le fonctionnement interne.
- **Tests d'acceptation** :
  - [ ] les catégories cochées sont enregistrées dans la clé `categories`, et seules les catégories
        autorisées sont proposées ;
  - [ ] une erreur de validation de l'API s'affiche sur le champ concerné ;
  - [ ] `npm run check` et `npm test` verts.

### BL-064 — Liens de l'email limités à http(s)

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : `newsletter.py` (`_LIEN`, `_segment_html`) pose `lien.url` dans `href` sans
  filtrer le schéma : le texte est échappé, mais un `javascript:` ou un `data:` venu d'un flux reste
  un lien cliquable dans l'email. Le site filtre déjà ces URL (`lien_sur` dans `api/sorties.py`,
  BL-047) : réutiliser la même règle dans la `Lettre`, et rendre le titre seul quand l'URL est
  refusée. Relevé à la relecture de BL-047.
- **Bénéfice attendu** : un flux hostile ne peut plus glisser de lien piégé dans le digest.
- **Tests d'acceptation** :
  - [ ] un article à URL `javascript:`, `data:` ou sans hôte n'a pas de lien, en HTML comme en
        texte, et son titre reste ;
  - [ ] une URL http(s) garde son lien ;
  - [ ] `--send-only` applique le même filtre.

### BL-050 — Étudier le catalogue de flux par métier

- **Catégorie** : docs
- **Priorité** : 2
- **Description** : étude, sans code. Les ~60 flux actuels couvrent la cyber, le réglementaire et la
  tech généraliste ; presque rien pour le QA, le produit, le design ou le pilotage DSI. Pour chaque
  thématique métier, proposer les catégories FreshRSS et 5 à 10 flux francophones et anglophones
  vérifiés : RSS valide, texte intégral ou non (lien avec BL-020), volume quotidien, langue. Repérer
  les flux actuels qui sont propres à TransfertPro et doivent passer en privé.
- **Bénéfice attendu** : savoir quelles sources ajouter avant d'ouvrir à un métier.
- **Tests d'acceptation** :
  - [ ] un document dans `docs/` : catégories par métier, flux proposés et leurs caractéristiques,
        flux actuels à passer en privé.

### BL-051 — Réorganiser le FreshRSS en catégories par métier

- **Catégorie** : exploitation
- **Priorité** : 2
- **Dépend de** : BL-050, BL-037
- **Description** : sur l'instance, regrouper les flux en catégories par thématique métier, ajouter
  les flux retenus par l'étude, isoler la veille concurrentielle TransfertPro dans des catégories
  privées, et tenir le catalogue de BL-037 à jour. Renommer une catégorie change son slug de sortie
  et son seuil éventuel (`RSSRESUME_CATEGORY_THRESHOLDS`) : à vérifier dans la même passe.
- **Bénéfice attendu** : le catalogue offert aux inscrits existe réellement.
- **Tests d'acceptation** :
  - [ ] chaque catégorie FreshRSS figure au catalogue, avec sa visibilité ;
  - [ ] un passage `--dry-run` sur un profil externe ne lit aucune catégorie privée.

### BL-029 — Augmenter le score d'un sujet repris par plusieurs catégories

- **Catégorie** : pipeline
- **Priorité** : 3
- **Description** : l'audio du mode `global` fusionne déjà les doublons inter-catégories. Restent :
  l'email, qui montre deux sections pour le même sujet ; le mode `category`, dupliqué par
  construction ; et surtout **l'incrément de score** — un fait repris par trois flux de trois
  catégories est objectivement plus important qu'un fait rapporté une fois, et rien ne l'exploite.
  Cela demande une passe globale **avant** sélection (dédoublonnage par URL exacte, puis par
  similarité de titre), donc un changement d'architecture de `digest.py` : plan à faire valider,
  avec l'impact sur le cache de scoring par tags et sur les erreurs partielles.
- **Bénéfice attendu** : le signal « beaucoup de sources en parlent » entre dans la sélection, et
  l'email cesse de répéter un sujet.
- **Tests d'acceptation** :
  - [ ] deux articles de même URL dans deux catégories ne forment qu'un sujet, rattaché à une seule ;
  - [ ] un sujet couvert par N sources reçoit un score supérieur au même sujet couvert une fois ;
  - [ ] le cache de scoring relu des tags reste valide (pas de re-scoring induit) ;
  - [ ] l'échec d'une catégorie n'empêche pas les autres d'aboutir.

### BL-034 — Noter les résumés sur le site pour affiner son profil

- **Catégorie** : web
- **Priorité** : 3
- **Description** : sur le site, chaque personne peut noter un résumé ou un article retenu (utile /
  hors sujet) et dire quels sujets elle veut voir davantage. Ces retours sont stockés par profil et
  proposés comme amendements du profil de pertinence — jamais appliqués sans validation — et
  pourront alimenter le jeu d'évaluation (BL-035).
- **Bénéfice attendu** : le profil s'ajuste sur l'usage réel au lieu d'être réécrit à la main.
- **Tests d'acceptation** :
  - [ ] une note est enregistrée pour le bon profil et la bonne journée, via l'API authentifiée ;
  - [ ] une personne ne peut noter que les journées de son propre profil ;
  - [ ] les retours accumulés produisent une proposition d'amendement lisible, appliquée seulement
        après confirmation ;
  - [ ] tests côté API (unittest) et côté site.

### BL-042 — Prompts et éphéméride sans biais cyber

- **Catégorie** : prompts
- **Priorité** : 3
- **Description** : `EPHEMERIDE_SYSTEM` ouvre « une lettre de veille en cybersécurité » et cherche
  d'abord un événement cyber, et la table `ephemeride/histoire.py` suit. Les exemples des consignes
  d'ouverture, de clôture, de sommaire et de conclusion citent Fortinet, la CNIL, « une faille sur un
  composant que vous exploitez », et interdisent un « rappel que la sécurité est un enjeu » qui
  suppose un contenu cyber. Ces exemples orientent tous les digests. Rendre l'éphéméride « tech et
  informatique » par défaut (le domaine éventuellement donné par le gabarit), élargir la table de
  repli, et choisir des exemples variés ou neutres. L'éphéméride est un appel par journée et non
  par profil : si son domaine devient personnel, chiffrer le coût.
- **Bénéfice attendu** : un dev ou un designer n'entend plus un digest qui sonne comme une lettre
  de RSSI.
- **Tests d'acceptation** :
  - [ ] le prompt d'éphéméride ne mentionne plus la cybersécurité par défaut ;
  - [ ] la table de repli couvre des événements hors sécurité ;
  - [ ] les tests existants des consignes restent verts, adaptés aux nouveaux exemples.

### BL-048 — Aperçu du profil : ce qu'il aurait retenu hier

- **Catégorie** : web
- **Priorité** : 3
- **Dépend de** : BL-038
- **Description** : sur la page profil, un bouton « aperçu » note les articles de la veille, déjà
  lus compris, avec le profil en cours d'édition (non enregistré), et montre ceux qui passeraient le
  seuil, avec note et angle. C'est la boucle d'apprentissage qui manque : on écrit son profil, on
  voit l'effet, on corrige. L'aperçu coûte un scoring complet : le limiter par profil et par jour,
  et n'écrire aucun tag dans FreshRSS.
- **Bénéfice attendu** : un profil réglé le premier jour au lieu d'une semaine de digests ratés.
- **Tests d'acceptation** :
  - [ ] l'aperçu ne pose aucun tag et ne marque rien comme lu ;
  - [ ] la limite par profil est appliquée et dite à l'écran ;
  - [ ] le coût de l'aperçu est journalisé à part ;
  - [ ] tests API avec une doublure LLM.

### BL-049 — Administration : désactiver et supprimer un compte

- **Catégorie** : web
- **Priorité** : 3
- **Description** : `/admin` est en lecture seule. Avec des inscriptions ouvertes, l'admin doit pouvoir
  suspendre un profil (la tournée ne le sert plus, ses données restent) et supprimer un compte (même
  chemin que la suppression par la personne, BL-043). Afficher aussi, par profil, le coût des sept
  derniers jours lu des journaux, pour repérer un profil qui coûte anormalement cher.
- **Bénéfice attendu** : répondre à un abus ou à une demande sans `docker exec`.
- **Tests d'acceptation** :
  - [ ] un profil suspendu n'est pas servi par la tournée et le log le dit ;
  - [ ] seules les personnes admin accèdent aux actions ;
  - [ ] tests API et tests du site.

### BL-026 — Écrire l'argument du choix de fournisseur LLM

- **Catégorie** : docs
- **Priorité** : 4
- **Description** : la mécanique est faite (`RSSRESUME_PROVIDER`, une clé par fournisseur,
  `llm/providers.json`). Reste à écrire dans le README que le **contenu envoyé au modèle** — ce
  qu'un éditeur SecNumCloud surveille chaque matin — est une donnée sensible en soi, et que le
  choix du fournisseur est donc une décision, pas un réglage.
- **Bénéfice attendu** : une décision de souveraineté écrite avant qu'on la demande.
- **Tests d'acceptation** :
  - [ ] le README a une section « Choix du fournisseur » de trois paragraphes environ ;
  - [ ] elle renvoie au mécanisme existant sans le redécrire.

### BL-025 — Faire le ménage dans les libellés de scoring

- **Catégorie** : freshrss
- **Priorité** : 4
- **Description** : les libellés `<profil>-score-NN` et un `<profil>-scoring-<hash>` par version de
  prompt s'accumulent dans la barre latérale FreshRSS, comme les anciens libellés sans préfixe.
  Ajouter une commande de maintenance qui liste les libellés correspondant à ces motifs avec le
  nombre d'articles portant chacun, et supprime via l'API Google Reader les `scoring-<hash>`
  obsolètes (empreinte différente de la courante) et les libellés sans préfixe. Simulation par
  défaut, suppression seulement avec un drapeau explicite.
- **Bénéfice attendu** : une barre latérale lisible, sans geste manuel.
- **Tests d'acceptation** :
  - [ ] sans drapeau, rien n'est supprimé et la liste est affichée ;
  - [ ] avec le drapeau, seuls les libellés obsolètes partent, jamais l'empreinte courante ;
  - [ ] tests avec une doublure du client FreshRSS, sans réseau.

### BL-036 — Skill de diagnostic « le digest n'est pas arrivé »

- **Catégorie** : outillage
- **Priorité** : 4
- **Description** : le runbook existe en prose dans CLAUDE.md (« Exploitation »). En faire une skill
  `.claude/skills/digest-absent/` qui le déroule dans l'ordre : résolution du domaine de
  `SMTP_FROM` (NS, A, MX, SPF), puis journaux `<categorie>.log.json` de la journée, puis transport
  (`RSSRESUME_MAIL_TRANSPORT`), puis logs du conteneur — en s'arrêtant à la première cause trouvée.
- **Bénéfice attendu** : un diagnostic en une commande, qui ne réinvestigue pas le SMTP filtré.
- **Tests d'acceptation** :
  - [ ] la skill ne lit jamais `.env` ni `.env.local` ;
  - [ ] elle conclut sur une cause, ou sur la liste de ce qui a été vérifié sain.

### BL-053 — Étudier la veille concurrentielle privée par profil

- **Catégorie** : docs
- **Priorité** : 4
- **Dépend de** : BL-037, BL-038
- **Description** : étude, sans code. Chacun déclare ses concurrents (et des mots-clés) dans son
  profil, et le système crée les flux correspondants dans une catégorie privée à son nom : alertes
  Google, recherches Google News en RSS, flux des blogs et des pages presse des concurrents. À
  vérifier : création de flux et de catégories par l'API de FreshRSS (`subscription/edit`,
  `quickadd`), nombre de flux par personne et leur effet sur le rafraîchissement du FreshRSS
  partagé, suppression des flux quand un concurrent est retiré, confidentialité (ces flux disent ce
  que la personne surveille), contenu tronqué (BL-020).
- **Bénéfice attendu** : rendre aux externes ce que la veille TransfertPro a de plus utile, sans
  la leur montrer.
- **Tests d'acceptation** :
  - [ ] un document court dans `docs/` : faisabilité par l'API, limites, coût, recommandation.

### BL-027 — Étudier le digest réinjecté comme entrée RSS

- **Catégorie** : docs
- **Priorité** : 5
- **Description** : étude, sans code. Faire du digest un article synthétique dans un flux FreshRSS
  **dédié** (jamais dans les flux sources, contrairement à xExtension-FeedDigest), disponible dans
  les clients mobiles. Vérifier d'abord si l'API Google Reader de FreshRSS permet l'insertion, ce
  qui n'est pas acquis ; comparer avec un flux RSS statique généré et souscrit, et avec l'email.
- **Bénéfice attendu** : décider sur pièces si un client mobile devient un vrai besoin.
- **Tests d'acceptation** :
  - [ ] un document court dans `docs/` : faisabilité, alternative, comparaison, recommandation.
