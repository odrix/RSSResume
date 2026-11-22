# Backlog — traité

Les items sortis de [backlog-todo.md](backlog-todo.md), dans l'ordre de réalisation. Chaque entrée
garde ses champs d'origine et gagne **Réalisé le** et **Livraison** ; les écarts au texte initial,
actés à la relecture, vont dans **Notes**. Un item écarté y figure aussi, avec la raison.

Les nouvelles entrées s'ajoutent **en fin de fichier** : `.gitattributes` y pose `merge=union`,
pour que deux branches traitées en parallèle n'entrent pas en conflit ici.

Les entrées BL-001 à BL-031 sont reprises de `totorss.md` (date : commit qui a coché l'item, ou à
défaut celui du code) ; BL-032 et BL-033 de `todo-improve.md`. Leurs tests d'acceptation n'avaient
pas été écrits à l'époque : la ligne en tient lieu renvoie aux tests qui couvrent le comportement.

---

### BL-001 — Injecter le profil dans le prompt de résumé

- **Catégorie** : prompts
- **Priorité** : 1
- **Description** : le profil de pertinence ne servait qu'au scoring ; le texte écouté était rédigé
  par un modèle qui ignorait qui l'écoute.
- **Bénéfice attendu** : le plus gros gain de qualité de la liste, pour une ligne.
- **Tests d'acceptation** : le prompt envoyé contient le profil (`tests/test_summaries.py`).
- **Réalisé le** : 2026-08-24
- **Livraison** : PR #4

### BL-002 — Demander la fusion des sujets redondants

- **Catégorie** : prompts
- **Priorité** : 1
- **Description** : plusieurs dépêches sur le même fait donnaient plusieurs points ; une consigne de
  fusion, avec citation des sources, en fait un seul.
- **Bénéfice attendu** : 80 % d'un clustering sémantique pour zéro appel de plus.
- **Tests d'acceptation** : présence de la consigne de fusion dans le prompt.
- **Réalisé le** : 2026-08-24
- **Livraison** : PR #4

### BL-003 — Attribuer les sources par nom de flux

- **Catégorie** : prompts
- **Priorité** : 1
- **Description** : chaque point cite son flux entre parenthèses, jamais l'URL (risque
  d'hallucination) ; l'URL sort du payload et les liens passent dans le corps de l'email.
- **Bénéfice attendu** : « va lire ça » plutôt que « voici ce que ça dit », garde-fou de l'axe
  réglementaire.
- **Tests d'acceptation** : payload sans `url`, liens présents dans l'email.
- **Réalisé le** : 2026-08-24
- **Livraison** : PR #4

### BL-008 — Garde anti-injection dans les prompts

- **Catégorie** : prompts
- **Priorité** : 1
- **Description** : tout texte d'article est une donnée, jamais une instruction ; contenu encadré
  par un délimiteur explicite dans le message utilisateur.
- **Bénéfice attendu** : mitigation gratuite d'un billet piégé qui ferait minorer une CVE.
- **Tests d'acceptation** : test avec un article contenant une tentative d'injection.
- **Réalisé le** : 2026-08-27
- **Livraison** : PR #8

### BL-009 — Corriger `strip_html`

- **Catégorie** : pipeline
- **Priorité** : 1
- **Description** : le corps des `<script>`, `<style>`, `<noscript>`, `<template>` partait au
  modèle ; réécrit sur `html.parser`.
- **Bénéfice attendu** : plus de code ni de texte masqué envoyé en prompt.
- **Tests d'acceptation** : `tests/test_text.py` (script, style, commentaire, chevron en attribut).
- **Réalisé le** : 2026-08-27
- **Livraison** : PR #8

### BL-010 — Consigner l'échappement de la sortie du modèle

- **Catégorie** : docs
- **Priorité** : 2
- **Description** : la sortie d'un modèle nourri de contenu non fiable est non fiable ; tout rendu
  HTML doit l'échapper. Note dans FONCTIONNEMENT.md, « Contraintes de sécurité ».
- **Bénéfice attendu** : pas de XSS *à travers* le modèle le jour où une vue HTML apparaît.
- **Tests d'acceptation** : section présente dans FONCTIONNEMENT.md.
- **Réalisé le** : 2026-08-27
- **Livraison** : PR #8

### BL-016 — Filtrer côté API dans `fetch_daily_articles`

- **Catégorie** : freshrss
- **Priorité** : 1
- **Description** : `ot` et `xt` de l'API Google Reader au lieu de paginer tout le flux puis
  filtrer en Python.
- **Bénéfice attendu** : quelques appels HTTP au lieu de dizaines chaque jour.
- **Tests d'acceptation** : `tests/test_freshrss.py`, pagination par continuation comprise.
- **Réalisé le** : 2026-08-27

### BL-007 — Trancher le sort de `summarize_top`

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : fonction documentée comme deuxième étage du pipeline, jamais appelée.
- **Bénéfice attendu** : une documentation qui décrit ce que le code fait.
- **Tests d'acceptation** : la doc et le code concordent.
- **Réalisé le** : 2026-08-27
- **Notes** : tranché en (c). `summarize_top` n'existe plus ; `summarize_article` reste comme outil
  de mise au point hors pipeline (`python -m rssresume.llm.processing`), avec son action `article`
  dans `providers.json`, et FONCTIONNEMENT.md le dit.

### BL-011 — Retry et backoff sur les appels réseau

- **Catégorie** : pipeline
- **Priorité** : 1
- **Description** : 3 tentatives, backoff exponentiel avec jitter sur 429/5xx et erreurs de
  connexion, respect de `Retry-After`, jamais sur un autre 4xx.
- **Bénéfice attendu** : un hoquet de fournisseur ne supprime plus le digest du jour.
- **Tests d'acceptation** : `tests/test_http.py`, doublure qui échoue N fois.
- **Réalisé le** : 2026-08-28
- **Notes** : dans `tools/http.py`.

### BL-012 — Dégrader proprement sur lot de scoring incomplet

- **Catégorie** : pipeline
- **Priorité** : 1
- **Description** : une note manquante donnait une exception qui tuait toutes les catégories ;
  désormais score 0, thématique « autre », avertissement.
- **Bénéfice attendu** : 39 notes sur 40 ne coûtent plus la journée.
- **Tests d'acceptation** : lot complet, note manquante, id dupliqué, réponse vide.
- **Réalisé le** : 2026-08-28

### BL-013 — Redécouper au lieu de lever sur réponse tronquée

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : `finish_reason == "length"` en scoring relance avec un lot divisé par deux,
  jusqu'à 5 articles.
- **Bénéfice attendu** : la journée s'adapte au lieu de mourir.
- **Tests d'acceptation** : redécoupage tracé, levée immédiate pour les autres actions.
- **Réalisé le** : 2026-08-28

### BL-014 — Plafonner l'entrée du chemin résumé

- **Catégorie** : pipeline
- **Priorité** : 1
- **Description** : troncature par article sur frontière de phrase, `max_tokens` explicite, volume
  tracé par catégorie.
- **Bénéfice attendu** : plus d'appel à 100 000 caractères sans garde-fou.
- **Tests d'acceptation** : `truncate_sentences` dans `tests/test_text.py`.
- **Réalisé le** : 2026-08-28

### BL-015 — Découper les journées en Europe/Paris

- **Catégorie** : freshrss
- **Priorité** : 1
- **Description** : bornes de journée en `zoneinfo`, fuseau `RSSRESUME_TIMEZONE`.
- **Bénéfice attendu** : un article de 1 h du matin en été tombe dans la bonne journée.
- **Tests d'acceptation** : article à 00 h 30 heure de Paris en été.
- **Réalisé le** : 2026-08-28

### BL-004 — Faire remonter `thematique` et `angle` jusqu'au résumé

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : champs payés au scoring puis jetés ; ils orientent maintenant le résumé.
- **Bénéfice attendu** : le contexte « pourquoi ça compte pour toi », sans appel de plus.
- **Tests d'acceptation** : `tests/test_digest.py`, `tests/test_summaries.py`.
- **Réalisé le** : 2026-08-30

### BL-005 — Regrouper le digest par thématique

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : l'audio sautait du réglementaire au cyber au gré des scores.
- **Bénéfice attendu** : une écoute suivable.
- **Tests d'acceptation** : couverture du regroupement par thématique.
- **Réalisé le** : 2026-08-30
- **Notes** : deux écarts assumés. (1) L'ordre des thématiques est dynamique : chaque groupe est
  classé sur son meilleur article (`_grouped_by_theme`), pour qu'une faille critique ne passe pas
  derrière une routine réglementaire ; `THEMATIQUES` ne sert qu'à valider. (2) L'ouverture
  n'annonce pas les rubriques : une phrase qui juge la journée, des transitions sans sommaire.

### BL-006 — Passer en prose pour l'audio

- **Catégorie** : prompts
- **Priorité** : 2
- **Description** : des puces lues par un TTS donnent un débit haché ; prose continue, longueur en
  nombre de sujets.
- **Bénéfice attendu** : un audio qui s'écoute.
- **Tests d'acceptation** : paliers de profondeur figés par test.
- **Réalisé le** : 2026-08-30

### BL-023 — Aligner `BULLET_TIERS` sur la plage atteignable

- **Catégorie** : prompts
- **Priorité** : 4
- **Description** : paliers à 15 et 35 articles inatteignables sous le plafond de 12.
- **Bénéfice attendu** : plus de configuration morte.
- **Tests d'acceptation** : `test_the_thresholds_stay_reachable_under_the_selection_cap`.
- **Réalisé le** : 2026-08-30
- **Notes** : alignés, pas supprimés — `prompts.DEPTH_TIERS` à 3 et 8, plus `DEPTH_DEFAULT`.

### BL-017 — Comptabiliser les tokens et le coût

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : bloc `usage` remonté, agrégé par action et catégorie, récapitulatif en fin
  d'exécution, tarifs configurables.
- **Bénéfice attendu** : voir dériver la ligne de scoring avant la facture.
- **Tests d'acceptation** : `tests/test_runlog.py`, `tests/test_pricing.py`.
- **Réalisé le** : 2026-08-30

### BL-019 — Traiter les avis CERT-FR de façon déterministe

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : appariement sur la stack déclarée, une phrase pour les avis qui la touchent, les
  autres marqués lus sans LLM.
- **Bénéfice attendu** : l'essentiel de la facture et le pire de l'audio supprimés.
- **Tests d'acceptation** : `tests/test_certfr.py`.
- **Réalisé le** : 2026-08-30

### BL-031 — Sortir l'audio de journée de l'ordre des dossiers FreshRSS

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : `MontageService` part des articles de la journée, réordonnés, et non des
  résumés de catégorie dans l'ordre des dossiers.
- **Bénéfice attendu** : le sujet le plus grave n'arrive plus huitième parce que son dossier est le
  dernier ; les numéros de version ne traversent plus deux réécritures.
- **Tests d'acceptation** : `tests/test_montage.py`.
- **Réalisé le** : 2026-09-07

### BL-030 — Graduer le détail des CVE sur la stack déclarée

- **Catégorie** : prompts
- **Priorité** : 2
- **Description** : appariement de chaque article sur la clé `stack` du profil ; plage touchée et
  version corrigée si le composant est exploité, une phrase sans numéro sinon.
- **Bénéfice attendu** : la CVE qui demande une action n'est plus enterrée sous six numéros de
  version récités.
- **Tests d'acceptation** : stack vide = rien de gradué.
- **Réalisé le** : 2026-09-19

### BL-032 — Plusieurs profils, pour plusieurs personnes

- **Catégorie** : pipeline
- **Priorité** : 2
- **Description** : le passage quotidien sert chaque profil, profils en base SQLite, sorties
  rangées sous l'identifiant du profil, tags FreshRSS préfixés.
- **Bénéfice attendu** : RSSResume utilisable par d'autres que son auteur.
- **Tests d'acceptation** : `tests/test_multiprofil.py`, `tests/test_annuaire_sqlite.py`.
- **Réalisé le** : 2026-11-19

### BL-033 — Sorties en ligne et site de présentation

- **Catégorie** : web
- **Priorité** : 2
- **Description** : API HTTP des profils et des journées, site SvelteKit (comptes, profil, résumés
  audio), application Dokploy distincte jointe par `dokploy-network`.
- **Bénéfice attendu** : écouter et gérer son digest sans accès au serveur.
- **Tests d'acceptation** : `tests/test_api.py`, tests du site.
- **Réalisé le** : 2026-11-19

### BL-028 — Passerelle LLM ou code de résilience

- **Catégorie** : docs
- **Priorité** : 5
- **Description** : arbitrage entre retry maison et une passerelle type Portkey auto-hébergée.
- **Bénéfice attendu** : ne pas exploiter un service de trop.
- **Tests d'acceptation** : décision écrite.
- **Réalisé le** : 2026-11-21
- **Notes** : tranché en (a) par les faits — retry dans `tools/http.py` (BL-011), routage par
  action via `RSSRESUME_<ACTION>_PROVIDER`, cache dans les tags FreshRSS, coût dans `runlog.py`.

### BL-018 — Résumé en texte délimité plutôt qu'en JSON — écarté

- **Catégorie** : prompts
- **Priorité** : 5
- **Description** : économiser les accolades du JSON dans le payload du résumé.
- **Bénéfice attendu** : 15 à 20 % de tokens.
- **Tests d'acceptation** : —
- **Réalisé le** : 2026-11-21 (écarté)
- **Notes** : contre-indiqué. Le payload porte `thematique`, `angle` et `stack`, et les consignes
  s'y réfèrent par nom de champ : le JSON est ce qui les rend adressables. Le gain porterait sur des
  accolades, quand l'essentiel du volume est `content`.


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
  - [x] chaque valeur produit la consigne attendue dans `digest_user` et `montage_user` ;
  - [x] clé absente : consigne identique à l'actuelle ;
  - [x] valeur inconnue refusée par `profil_depuis_dict`.
- **Réalisé le** : 2026-11-22
- **Livraison** : branche backlog/BL-040-regime-securite
- **Notes** : `curieux` cite quand même, en une phrase, une faille qui touche la stack déclarée
  (décision prise au plan). Le régime n'entre pas dans l'empreinte de scoring : le changer ne fait
  pas renoter. Le site efface encore la clé quand il enregistre un profil : BL-054.

### BL-047 — Page des résumés : le texte et les articles, pas seulement l'audio

- **Catégorie** : web
- **Priorité** : 1
- **Description** : `/resumes/<username>` n'affiche que des lecteurs audio. Ni texte, ni articles,
  ni liens, et les journées sans audio n'apparaissent pas. Or les journaux `<categorie>.log.json`
  portent tout ce que montre l'email. Exposer par l'API le contenu d'une journée lu des journaux
  (résumés, articles retenus avec lien et source, articles « à surveiller »), et l'afficher avec
  l'audio. Journée sans article : visible, avec sa raison. État vide : dire à quelle heure arrive le
  premier résumé.
- **Bénéfice attendu** : le site devient un endroit où lire sa veille, pas seulement l'écouter, et
  l'audio en lien de BL-044 a une page où atterrir.
- **Tests d'acceptation** :
  - [x] la route API rend le contenu d'une journée à son seul propriétaire (ou à un admin) ;
  - [x] les liens d'articles sont échappés (sortie de modèle et contenu de flux non fiables) ;
  - [x] une journée sans audio est listée ;
  - [x] tests API en unittest, tests du site.
- **Réalisé le** : 2026-11-22
- **Livraison** : branche backlog/BL-047-page-resumes
- **Notes** : l'API n'a que le jeton du site, donc le contrôle propriétaire/admin se fait côté site
  (`ConsultationResumes`), comme pour l'audio. Les URL non http(s) sont retirées deux fois (API et
  site), et aucun composant n'utilise `{@html}`. Une journée en cours d'écriture répond `en_cours`
  au lieu d'une erreur ou d'une journée vide. L'heure annoncée est celle du début du passage :
  `RSSRESUME_SCHEDULE` et `RSSRESUME_TIMEZONE` sont désormais aussi posées sur le service `api` du
  compose. Le même défaut de liens existe dans l'email : BL-064.


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
  - [x] un document court dans `docs/` : coût mesuré, options, recommandation, seuils de bascule ;
  - [x] les items de code qui en découlent sont ajoutés à ce backlog.
- **Réalisé le** : 2026-11-22
- **Livraison** : branche backlog/BL-052-etude-cout
- **Notes** : [docs/cout-et-passage-a-l-echelle.md](docs/cout-et-passage-a-l-echelle.md), mesuré
  sur dix journées de production de septembre 2026, un profil. Le tarif de `gpt-5.6-luna` manque à
  la grille : le coût est donné en deux bornes (0,09 à 0,17 $ par profil et par jour). Le scoring
  ne pèse que 2 % ; la voix, le résumé et le montage font le reste — le scoring mutualisé par
  gabarit n'est donc pas retenu. Items créés : BL-055 à BL-063 ; BL-025 passe en priorité 2 et
  dépend de BL-056.

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
  - [x] le fichier est validé au chargement ; une entrée fautive lève au lancement ;
  - [x] une catégorie privée n'atteint ni le scoring, ni le résumé, ni l'email d'un non-propriétaire ;
  - [x] une catégorie FreshRSS absente du catalogue n'est servie à personne, et le log le dit ;
  - [x] le marquage comme lu de la tournée reste inchangé ;
  - [x] README et FONCTIONNEMENT décrivent le fichier.
- **Réalisé le** : 2026-11-22
- **Livraison** : branche backlog/BL-037-catalogue-categories
- **Notes** : le catalogue ne vit pas dans un fichier mais dans une table `categories` de la base des
  profils (`RSSRESUME_PROFILES_DB`), choix fait au plan : le vrai catalogue nomme la veille privée et
  ses propriétaires, il reste hors du dépôt. Le JSON reste le format d'échange, importé par
  `python -m rssresume.api importer-catalogue <fichier>` ; le dépôt n'en versionne qu'un exemple
  générique (`docs/categories.exemple.json`). Sans catalogue, un profil seul est servi comme avant ;
  à deux profils ou plus la tournée refuse de démarrer — y compris en mode dossier, qui doit donc
  passer à la base. Les catégories servies à personne restent marquées lues, comme avant. Hors
  périmètre : `--send-only` d'une journée produite avant l'import renvoie ses journaux tels quels.
