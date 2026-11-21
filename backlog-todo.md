# Backlog — à faire

Le seul backlog du dépôt. Les items traités partent dans [backlog-done.md](backlog-done.md),
avec leur date de réalisation ; `/backlog-pop` les traite (voir
[la skill](.claude/skills/backlog-pop/SKILL.md)).

Repris le 2026-11-21 de `totorss.md` (les numéros d'item y sont conservés : BL-020 est
l'item 20) et de `todo-improve.md`. Les actions de déploiement ponctuelles restent dans
`todo-dockploy.md`, gitignoré : ce sont des gestes sur une instance, pas des évolutions.

## Règles

- **Identifiant** `BL-NNN`, jamais réattribué. Prochain libre : **BL-037**.
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
- **Priorité** : 2
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
- **Priorité** : 2
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
