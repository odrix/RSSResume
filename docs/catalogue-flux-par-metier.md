# Catalogue de flux par métier

Étude BL-050 : quelles catégories FreshRSS et quels flux ajouter avant d'ouvrir le digest à un
métier. Aucun code ; la création des catégories et l'ajout des flux relèvent de BL-051, le texte
intégral des flux tronqués de BL-020, les gabarits par métier de BL-041.

Les ~60 flux actuels couvrent la cybersécurité, le réglementaire et la tech généraliste. Ils
servent le CTO, le développeur, l'ops et le RSSI ; ils ne servent presque pas le QA, le PO/PM, le
designer, le chef de projet ni le pilotage d'une DSI. C'est là que porte l'effort.

## 1. Contexte et méthode

**Date de vérification : 2026-11-22.** Fenêtre de volume : les sept jours qui précèdent
(2026-11-15 → 2026-11-22, un dimanche : les sites de presse ne publient pas le week-end, le
volume réel en semaine est un peu plus haut que la moyenne affichée).

Chaque flux a été vérifié en récupérant **l'URL du flux elle-même**, pas la page HTML du site :

| Critère | Règle |
|---|---|
| Valide | HTTP 200 et racine `<rss>`, `<feed>` (Atom) ou `<rdf:RDF>`, XML bien formé. Une redirection vers une page HTML ou un JSON écarte le flux. |
| Volume | items datés des 7 derniers jours ÷ 7. Quand **tous** les items du flux tombent dans la fenêtre, le flux plafonne : le volume est noté « ≥ », estimé sur l'intervalle réellement couvert. Un flux sans item sur 7 jours est estimé sur l'intervalle entre son plus ancien et son plus récent item. |
| Texte intégral | `content:encoded` (RSS) ou `<content>` (Atom) nettement plus long que `description` / `summary` : **intégral**. Moins d'environ 500 caractères de texte, ou « Lire la suite » : **tronqué**. Entre les deux (1 000 à 2 000 caractères pour des articles visiblement plus longs) : **partiel**. Les longueurs sont des médianes, balises HTML retirées. |
| Langue | `<language>` (ou `xml:lang`), sinon les titres. |
| Écarté | dernier item à plus de 60 jours, flux payant ou derrière une connexion, flux vide, URL de flux introuvable. |

Un flux qui n'a pu être vérifié n'apparaît pas aux tableaux : il est listé à part, en section 4.7.

Les sources retenues sont publiques et généralistes du métier : pas de blog d'éditeur centré sur
ses propres annonces, rien qui vise une entreprise ou un marché précis.

## 2. Inventaire actuel et flux à passer en privé

Le dépôt est public : l'inventaire des flux actuels, et donc la liste de ceux à passer en privé,
**ne figurent pas ici**. Ils se produisent hors dépôt :

1. Dans FreshRSS : *Abonnements › Importer / exporter › Exporter*, au format OPML.
2. Soumettre ce fichier à un chat IA avec le prompt de l'[annexe](#annexe--prompt-dinventaire-opml).
3. Conserver le résultat dans `input/` (gitignoré), à côté du catalogue réel
   (`input/categories.json`).

Un flux passe en **privé** — catégorie `"visibilite": "privee"` avec ses `proprietaires` dans le
catalogue (BL-037) — dès qu'il remplit l'un de ces critères :

- c'est une alerte (Google Alerts ou équivalent) sur une entreprise, ses concurrents ou son
  marché ;
- il relève d'une veille concurrentielle nommée, même s'il vient d'une source publique ;
- il sert un projet personnel ou une activité annexe du propriétaire ;
- son titre ou son URL porte un nom d'entreprise ou de produit précis ;
- dans le doute : un flux qui n'a de sens que pour une seule personne est privé. Le catalogue est
  fermé par défaut, une catégorie privée de trop coûte moins qu'une veille exposée.

La règle s'applique à la **catégorie**, pas au flux : le catalogue décrit des catégories. Un flux
privé rangé dans une catégorie publique doit donc en sortir, vers une catégorie privée. C'est la
réorganisation de BL-051, qui en profite pour regrouper les flux publics par thématique métier.

La section 4 du prompt (doublons) sert aussi ici : plusieurs flux proposés plus bas — presse IT
française en particulier — figurent peut-être déjà dans l'instance. Recouper avant d'ajouter.

## 3. Catégories par métier

### Métiers

Les neuf métiers de BL-041 et de [categories.exemple.json](categories.exemple.json). Le champ
`metiers` du catalogue est encore libre ; les identifiants ci-dessous sont une proposition, dans
la forme de ceux déjà employés (`developpeur`, `cto`) — minuscules, sans accents :

| Identifiant proposé | Métier |
|---|---|
| `cto` | CTO, direction technique |
| `developpeur` | développeur |
| `ops` | ops, SRE, exploitation |
| `dsi` | DSI, pilotage du SI |
| `rssi` | RSSI |
| `chef-de-projet` | chef de projet |
| `qa` | QA, test |
| `po-pm` | Product Owner, Product Manager |
| `designer` | designer UX / UI |

### Conventions de nommage

Vérifiées dans [categories.exemple.json](categories.exemple.json) et le code :

- **Libellé de catégorie** : `N - Libellé`, sans accents (`1 - Alertes et avis CERT-FR ANSSI`,
  `Tech generaliste`). Les accents ne gênent pas l'appariement — `cle_categorie()`
  ([categories.py](../rssresume/categories.py)) compare sans casse ni accents — mais ils
  disparaissent du slug, autant ne pas les mettre. Les nouvelles catégories prennent les numéros
  **11 et suivants**.
- **Slug** : dérivé du libellé par `slugify()` ([tools/text.py](../rssresume/tools/text.py)) —
  minuscules, toute suite de caractères hors `a-z0-9` devient un `-`. `6 - Tech generaliste`
  donne `6-tech-generaliste`, qui nomme les fichiers de sortie (`<slug>.log.json`, `<slug>.mp3`).
  Un caractère accentué y deviendrait un tiret : `11 - Qualité logicielle` donnerait
  `11-qualit-logicielle`. Renommer une
  catégorie change donc son slug **et** la clé de son seuil dans `RSSRESUME_CATEGORY_THRESHOLDS`
  (BL-051).
- **Nom de flux** : `Source - Rubrique` (`Le Monde Informatique - Toutes les actualites`).

### Catégories proposées

| Catégorie FreshRSS proposée | Slug | Métiers | Description (pour le catalogue) |
|---|---|---|---|
| `11 - Qualite logicielle et tests` | `11-qualite-logicielle-et-tests` | `qa`, `developpeur` | Pratique du test, automatisation, qualité du code et des livraisons. |
| `12 - Gestion de produit` | `12-gestion-de-produit` | `po-pm`, `cto`, `designer` | Discovery, priorisation, organisation produit, rôle du PM. |
| `13 - Design et UX` | `13-design-et-ux` | `designer`, `po-pm`, `developpeur` | Recherche utilisateur, design d'interface, accessibilité, design graphique. |
| `14 - Gestion de projet et agilite` | `14-gestion-de-projet-et-agilite` | `chef-de-projet`, `po-pm`, `cto` | Pilotage de projet, Scrum et Kanban, organisation des équipes. |
| `15 - Pilotage DSI` | `15-pilotage-dsi` | `dsi`, `cto`, `rssi` | Stratégie et budgets IT, gouvernance, transformation, marché des DSI. |

Les métiers déjà servis (CTO, développeur, ops, RSSI) le restent par les catégories publiques
actuelles — tech généraliste, avis CERT-FR, cybersécurité, réglementaire — qui ne changent pas
dans cette étude. L'ops n'a pas de catégorie nouvelle : ses besoins (incidents, cloud,
vulnérabilités) sont ceux de la tech généraliste et de la cyber.

## 4. Flux proposés

Légende — **Format** : RSS 2.0 sauf mention. **Items 7 j** : items datés du 2026-11-15 au
2026-11-22. **Volume/j** : voir la méthode ; « ≥ » signale un flux plafonné.

### 4.1. `11 - Qualite logicielle et tests`

| Flux | URL du flux | Langue | Format | Valide | Texte | Items 7 j | Volume/j | Remarque |
|---|---|---|---|---|---|---|---|---|
| Software Testing Magazine - Articles | `https://www.softwaretestingmagazine.com/feed/` | en | RSS 2.0 | oui | partiel (~1 700 car.) | 5 | 0,7 | Le plus régulier du métier ; articles et annonces d'outils. |
| Martin Fowler - Blog | `https://martinfowler.com/feed.atom` | en | Atom | oui | intégral | 3 | 0,4 | Architecture et test (simulation, contrats de données) ; sert aussi le développeur. |
| Alan Page - Angry Weasel | `https://angryweasel.substack.com/feed` | en | RSS 2.0 | oui | intégral | 2 | 0,3 | Qualité en équipe, test et IA. |
| La Taverne du testeur - Articles | `https://latavernedutesteur.fr/feed/` | fr | RSS 2.0 | oui | tronqué (~480 car.) | 2 | 0,3 | Communauté francophone du test. |
| Google Testing Blog | `https://testing.googleblog.com/feeds/posts/default` | en | Atom | oui | intégral | 0 | < 0,1 | Dernier billet 2026-10-05 ; fiches courtes « Testing on the Toilet ». Redirige vers FeedBurner. |
| DevelopSense - Michael Bolton | `https://developsense.com/feed` | en | RSS 2.0 | oui | tronqué (~420 car.) | 0 | < 0,1 | Dernier billet 2026-11-03 ; test exploratoire, Rapid Software Testing. |
| Satisfice - James Bach | `https://www.satisfice.com/feed` | en | RSS 2.0 | oui | tronqué (~320 car.) | 0 | < 0,1 | Dernier billet 2026-10-01, proche de la limite des 60 jours. |

Couverture faible en volume (~2 articles par jour au total) et en français (une seule source).
Une catégorie aussi calme passe souvent sous le seuil : prévoir un seuil propre, ou la fusionner
avec la tech généraliste dans les gabarits plutôt que de la servir seule.

### 4.2. `12 - Gestion de produit`

| Flux | URL du flux | Langue | Format | Valide | Texte | Items 7 j | Volume/j | Remarque |
|---|---|---|---|---|---|---|---|---|
| Lenny's Newsletter | `https://www.lennysnewsletter.com/feed` | en | RSS 2.0 | oui | intégral, sauf billets payants | 5 | 0,7 | Référence du métier ; une partie des billets est réservée aux abonnés et arrive coupée. |
| Product Talk - Teresa Torres | `https://www.producttalk.org/feed/` | en | RSS 2.0 | oui | intégral | 4 | 0,6 | Discovery continue. Redirige vers `/rss/`. |
| The Beautiful Mess - John Cutler | `https://cutlefish.substack.com/feed` | en | RSS 2.0 | oui | intégral | 1 | 0,1 | Organisation produit, hebdomadaire. |
| SVPG - Marty Cagan | `https://www.svpg.com/feed/` | en | RSS 2.0 | oui | tronqué (~420 car.) | 0 | < 0,1 | Dernier billet 2026-11-06 ; modèle produit. |
| Roman Pichler - Blog | `https://www.romanpichler.com/feed/` | en | RSS 2.0 | oui | intégral | 0 | < 0,1 | Dernier billet 2026-10-05 ; stratégie produit, rôle du PO. |
| Qualitystreet - Blog | `https://www.qualitystreet.fr/feed/` | fr | RSS 2.0 | oui | tronqué (~350 car.) | 0 | 0,1 | Dernier billet 2026-11-10 ; agilité et posture du PO. Sert aussi la catégorie 14. |

Le volume (~1,5 par jour) et le français (une source) sont les deux manques. Aucun flux
francophone de gestion de produit vérifiable n'a été trouvé dans cette passe (voir 4.7).

### 4.3. `13 - Design et UX`

| Flux | URL du flux | Langue | Format | Valide | Texte | Items 7 j | Volume/j | Remarque |
|---|---|---|---|---|---|---|---|---|
| UX Collective | `https://uxdesign.cc/feed` | en | RSS 2.0 | oui | intégral | 10 | ≥ 1,4 | Plafonné à 10 items, tous de la semaine. Medium : certains billets réservés aux membres. |
| Nielsen Norman Group - Articles | `https://www.nngroup.com/feed/rss/` | en | RSS 2.0 | oui | partiel (~1 000 car.) | 4 | 0,6 | Recherche utilisateur ; articles longs, seule l'introduction arrive. |
| Smashing Magazine | `https://www.smashingmagazine.com/feed/` | en | RSS 2.0 | oui | intégral | 2 | 0,3 | Design d'interface, front, accessibilité ; sert aussi le développeur. |
| UX Planet | `https://uxplanet.org/feed` | en | RSS 2.0 | oui | tronqué | 8 | ≥ 1,1 | Plafonné à 10 items. Ligne éditoriale dérivée vers les outils d'IA : à garder à l'œil, premier à retirer. |
| Opquast - Blog | `https://www.opquast.com/feed/` | fr | RSS 2.0 | oui | partiel (~1 500 car.) | 1 | 0,1 | Qualité web, accessibilité, écoconception. |
| Access42 - Blog | `https://access42.net/feed` | fr | RSS 2.0 | oui | tronqué (~200 car.) | 0 | < 0,1 | Dernier billet 2026-11-10 ; accessibilité, RGAA. Redirige vers `/feed/`. |
| Graphéine - Blog | `https://www.grapheine.com/feed` | fr | RSS 2.0 | oui | tronqué (~220 car.) | 0 | < 0,1 | Dernier billet 2026-11-10 ; design graphique, identité visuelle. |

La catégorie la mieux pourvue des nouvelles (~3,5 par jour). Le volume repose sur deux flux
Medium plafonnés ; le français, sur trois flux calmes.

### 4.4. `14 - Gestion de projet et agilite`

| Flux | URL du flux | Langue | Format | Valide | Texte | Items 7 j | Volume/j | Remarque |
|---|---|---|---|---|---|---|---|---|
| Scrum.org - Blog | `https://www.scrum.org/resources/blog/rss.xml` | en | RSS 2.0 | oui | intégral (dans `description`) | 15 | 2,1 | Le plus gros volume du métier ; billets de formateurs, qualité inégale. |
| Blog Gestion de projet | `https://www.blog-gestion-de-projet.com/feed/` | fr | RSS 2.0 | oui | tronqué (~360 car.) | 3 | 0,4 | Méthodes et pratiques du chef de projet. |
| OCTO Talks | `https://blog.octo.com/feed` | fr | RSS 2.0 | oui | tronqué (~310 car.) | 3 | 0,4 | Delivery, lean, architecture ; sert aussi le CTO. |
| Johanna Rothman - Blog | `https://www.jrothman.com/feed/` | en | RSS 2.0 | oui | intégral | 1 | 0,1 | Gestion de projet, flux, risques. |
| Mountain Goat Software - Mike Cohn | `https://www.mountaingoatsoftware.com/blog/rss` | en | RSS 2.0 | oui | intégral | 0 | < 0,1 | Dernier billet 2026-11-10 ; Scrum, backlog. |
| Qualitystreet - Blog | voir 4.2 | fr | | | | | | Rangé en 12 ; un flux n'a qu'une catégorie dans FreshRSS. |

~3,4 articles par jour, dont 2 venus de Scrum.org : le seuil fera le tri.

### 4.5. `15 - Pilotage DSI`

| Flux | URL du flux | Langue | Format | Valide | Texte | Items 7 j | Volume/j | Remarque |
|---|---|---|---|---|---|---|---|---|
| Le Monde Informatique - Toutes les actualites | `https://www.lemondeinformatique.fr/flux-rss/thematique/toutes-les-actualites/rss.xml` | fr | RSS 2.0 | oui | tronqué (~400 car.) | 17 | 2,4 | Redirige vers `/rss.xml`. Presse IT généraliste : recouper avec la tech généraliste. |
| Silicon.fr | `https://www.silicon.fr/feed` | fr | RSS 2.0 | oui | intégral | 30 | 4,3 | Même remarque ; le plus riche en texte des flux français. |
| LeMagIT - Toutes les actualites | `https://www.lemagit.fr/rss/ContentSyndication.xml` | fr | RSS 2.0 | oui | tronqué (~230 car.) | 20 | ≥ 5 | Plafonné à 20 items (3 jours). Certains articles demandent une inscription gratuite. |
| IT for Business | `https://www.itforbusiness.fr/feed` | fr | RSS 2.0 | oui | tronqué (~370 car.) | 10 | ≥ 5 | Plafonné à 10 items (2 jours). Le plus centré DSI : budgets, portraits de DSI. |
| Cigref - Actualites | `https://www.cigref.fr/feed` | fr | RSS 2.0 | oui | tronqué (~500 car.) | 1 | 0,1 | Association des grandes DSI : rapports, gouvernance. |
| CIO.com | `https://www.cio.com/feed/` | en | RSS 0.92 | oui | intégral (dans `description`) | 20 | ≥ 7 | Plafonné à 20 items (3 jours). Gros volume. |
| ComputerWeekly - IT management | `https://www.computerweekly.com/rss/IT-management.xml` | en | RSS 2.0 | oui | tronqué (~160 car.) | 20 | ≥ 5 | Plafonné à 20 items. Rubrique pilotage, Royaume-Uni. |
| InformationWeek | `https://www.informationweek.com/rss.xml` | en | RSS 2.0 | oui | tronqué (~150 car.) | 9 | 1,3 | Stratégie IT, IA en entreprise. |
| MIT Sloan Management Review | `https://sloanreview.mit.edu/feed/` | en | RSS 2.0 | oui | intégral | 2 | 0,3 | Management et stratégie ; déborde du SI. |

Le problème est inverse des autres : **trop** de volume (~30 articles par jour à neuf flux). En
retenir cinq ou six au départ — IT for Business, Cigref, Le Monde Informatique ou Silicon.fr,
CIO.com, InformationWeek — et laisser le seuil de la catégorie faire le reste.

### 4.6. Écartés

| Source | URL essayée | Raison |
|---|---|---|
| Ministry of Testing | `https://www.ministryoftesting.com/feed` | redirige vers une page HTML |
| Software Testing Weekly | `https://softwaretestingweekly.com/feed` | 404 |
| Smartesting - Blog | `https://www.smartesting.com/feed/` | dernier billet 2026-09-03 (> 60 jours) ; flux valide et intégral, à reprendre s'il repart |
| Mind the Product | `https://www.mindtheproduct.com/feed/` | redirige vers une API JSON, pas un flux |
| Thiga | `https://www.thiga.co/feed` | 404 |
| Intercom - Blog | `https://www.intercom.com/blog/feed` | blog d'éditeur centré sur ses annonces |
| A List Apart | `https://alistapart.com/main/feed/` | dernier article 2026-06-30 (> 60 jours) |
| Blog du Modérateur - Design | `https://www.blogdumoderateur.com/design/feed/` | flux valide mais vide |
| Boxes and Arrows | `https://boxesandarrows.com/feed/` | publication arrêtée en 2022 |
| Esther Derby | `https://www.estherderby.com/feed/` | dernier billet 2026-05-08 (> 60 jours) |
| Alliancy | `https://www.alliancy.fr/feed` | redirige vers la page d'accueil |

### 4.7. À revérifier

| Source | URL essayée | Constat |
|---|---|---|
| Agile Alliance | `https://www.agilealliance.org/feed/` | connexion fermée sans réponse (blocage des clients automatisés probable) |
| Atlassian - Blog | `https://www.atlassian.com/blog/feed` | redirige vers la page HTML du blog ; une autre URL de flux existe peut-être |
| CIO Online | `https://www.cio-online.com/flux-rss/rss.xml` | certificat TLS expiré le jour de la vérification |

Manques à combler dans une seconde passe : un flux francophone de gestion de produit, un second
flux francophone de test.

## 5. Flux tronqués : candidats pour af_readability (BL-020)

Les flux où le résumé ne lirait qu'un chapô. BL-020 rappelle que l'extension enchaîne ses
requêtes sans délai : l'activer d'abord sur les flux **calmes**, et ne l'étendre aux flux à gros
volume qu'après avoir observé l'absence de limitation.

| Flux | Catégorie | Texte livré | Volume/j | Priorité |
|---|---|---|---|---|
| La Taverne du testeur | 11 | ~480 car. | 0,3 | calme : activer |
| DevelopSense | 11 | ~420 car. | < 0,1 | calme : activer |
| Satisfice | 11 | ~320 car. | < 0,1 | calme : activer |
| Software Testing Magazine | 11 | partiel, ~1 700 car. | 0,7 | si le résumé en souffre |
| SVPG | 12 | ~420 car. | < 0,1 | calme : activer |
| Qualitystreet | 12 | ~350 car. | 0,1 | calme : activer |
| Nielsen Norman Group | 13 | partiel, ~1 000 car. | 0,6 | calme : activer |
| Opquast | 13 | partiel, ~1 500 car. | 0,1 | si le résumé en souffre |
| Access42 | 13 | ~200 car. | < 0,1 | calme : activer |
| Graphéine | 13 | ~220 car. | < 0,1 | calme : activer |
| UX Planet | 13 | tronqué | ≥ 1,1 | après observation |
| Blog Gestion de projet | 14 | ~360 car. | 0,4 | calme : activer |
| OCTO Talks | 14 | ~310 car. | 0,4 | calme : activer |
| Cigref | 15 | ~500 car. | 0,1 | calme : activer |
| Le Monde Informatique | 15 | ~400 car. | 2,4 | après observation |
| LeMagIT | 15 | ~230 car. | ≥ 5 | après observation ; inscription parfois requise |
| IT for Business | 15 | ~370 car. | ≥ 5 | après observation |
| ComputerWeekly - IT management | 15 | ~160 car. | ≥ 5 | après observation |
| InformationWeek | 15 | ~150 car. | 1,3 | après observation |

Les flux intégraux — Silicon.fr, CIO.com, Scrum.org, Smashing Magazine, UX Collective, les
Substack — n'en ont pas besoin.

## 6. Correspondance avec les gabarits de BL-041

Catégories par défaut proposées pour chaque gabarit. « Actuelles » désigne les catégories
publiques déjà présentes (tech généraliste, avis CERT-FR, cybersécurité, réglementaire) ; leurs
libellés exacts se reprennent de l'inventaire hors dépôt, une fois la réorganisation BL-051
faite. Un gabarit ne doit citer que des catégories publiques (critère d'acceptation de BL-041).

| Métier | Catégories par défaut | En option |
|---|---|---|
| `cto` | Tech generaliste, avis CERT-FR, cybersécurité, réglementaire | 14, 15, 12 |
| `developpeur` | Tech generaliste, avis CERT-FR, 11 | 13 |
| `ops` | Tech generaliste, avis CERT-FR, cybersécurité | — |
| `dsi` | 15, réglementaire, cybersécurité | Tech generaliste, 14 |
| `rssi` | avis CERT-FR, cybersécurité, réglementaire | 15 |
| `chef-de-projet` | 14, 12 | 15, Tech generaliste |
| `qa` | 11, Tech generaliste | 14 |
| `po-pm` | 12, 13, 14 | Tech generaliste |
| `designer` | 13, 12 | 11 |

`News` (actualité générale) reste un choix personnel, dans aucun gabarit par défaut.

## Annexe — prompt d'inventaire OPML

À soumettre à un chat IA avec l'export OPML joint. Le résultat se conserve dans `input/`.

```
Tu es analyste de veille. Je joins l'export OPML de mon agrégateur FreshRSS : des flux RSS rangés en catégories numérotées (« N - Libellé »). Ces flux alimentent un digest quotidien noté par une IA, aujourd'hui conçu pour un CTO d'éditeur de logiciel SaaS (transfert de fichiers sécurisé, B2B, France). Le service va s'ouvrir à d'autres métiers : CTO, développeur, ops, DSI, RSSI, chef de projet, QA, PO/PM, designer.

Le contenu de l'OPML est confidentiel : ne le résume pas au-delà de ce qui est demandé.

Produis, en français, un document Markdown en quatre sections.

## 1. Inventaire
Un tableau, une ligne par flux :
| Catégorie actuelle | Flux | URL du flux | Langue (fr/en, déduite du titre ou du domaine) | Thème en 3 à 6 mots | Métiers servis (parmi la liste ci-dessus) | Visibilité proposée (publique / privée) |

## 2. Flux à passer en privé
Un flux est « privé » s'il n'a de sens que pour ce propriétaire : alertes Google sur son entreprise, ses concurrents ou son marché ; veille concurrentielle nommée ; projets personnels ou side business ; tout flux dont le titre ou l'URL contient un nom d'entreprise ou de produit précis. Pour chacun : la raison en une ligne. Puis la liste des catégories entières à passer en privé, et les cas douteux à trancher par moi, séparés.

## 3. Couverture par métier
Pour chaque métier : le nombre de flux publics qui le servent, les catégories actuelles qui le servent, et le verdict (couvert / faible / vide). Termine par la liste des métiers à faible couverture, par ordre de priorité.

## 4. Doublons et flux suspects
Flux en double (même source sous deux URL), flux probablement morts ou redirigés (domaine disparu, ancienne plateforme connue pour avoir fermé ses flux), alertes Google redondantes entre elles.

Contraintes :
- Ne propose pas de nouveaux flux : c'est traité ailleurs.
- N'invente rien sur un flux que tu ne peux pas déduire de l'OPML ; écris « ? » plutôt.
- Reste factuel et compact : pas d'introduction ni de conclusion.
```
