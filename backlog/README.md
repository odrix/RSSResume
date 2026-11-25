# Backlog

Le seul backlog du dépôt : **un fichier par item**. `todo/` porte ce qui reste à faire,
`done/` ce qui est traité, avec sa date. `/backlog-pop` traite les items (voir
[la skill](../.claude/skills/backlog-pop/SKILL.md)), `/backlog-raf` les compte par priorité.

## Pourquoi un fichier par item

Deux branches traitées en parallèle ne touchent jamais le même fichier : traiter un item, c'est
déplacer `todo/BL-NNN.md` vers `done/BL-NNN.md`, et rien d'autre. Un backlog en un seul fichier
entrait en conflit à chaque PR — le pilote `merge=union` de `.gitattributes` ne joue qu'en local,
GitHub ne l'applique pas à son bouton « Merge ».

## Règles

- **Identifiant** `BL-NNN`, jamais réattribué. Le prochain libre est le plus grand `BL-NNN` présent
  dans `todo/` **et** `done/`, plus un. Il n'y a pas de compteur à tenir à jour : un compteur
  partagé était lui-même une source de conflit. Deux items créés en parallèle dans deux branches
  peuvent se disputer un numéro : l'orchestrateur réserve les identifiants avant de lancer les
  agents.
- **Fichier** `BL-NNN.md`, qui s'ouvre sur `# BL-NNN — titre`, puis les champs ci-dessous.
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

- **Dépend de** (facultatif) : un item n'est pas pris tant que ses dépendances sont dans `todo/`.
- **Tests d'acceptation** : ce qui doit être vrai, et testé dans `tests/` quand c'est du code,
  pour que l'item parte dans `done/`.

## Un item traité

Il garde ses champs d'origine, ses cases cochées, et gagne **Réalisé le** et **Livraison** ; les
écarts au texte initial, actés à la relecture, vont dans **Notes**. Un item écarté va aussi dans
`done/`, avec la raison.

## Origine

BL-001 à BL-031 sont repris de `totorss.md` (les numéros d'item y sont conservés : BL-020 est
l'item 20 ; date : commit qui a coché l'item, ou à défaut celui du code), BL-032 et BL-033 de
`todo-improve.md`. Leurs tests d'acceptation n'avaient pas été écrits à l'époque : la ligne qui
en tient lieu renvoie aux tests qui couvrent le comportement. Les actions de déploiement
ponctuelles restent dans `todo-dockploy.md`, gitignoré : ce sont des gestes sur une instance, pas
des évolutions.

BL-037 à BL-053 viennent de l'étude d'ouverture du 2026-11-22 : servir des personnes extérieures
à l'exploitant (CTO, dev, DSI, RSSI, chef de projet, QA, PO/PM, designer). Décisions prises :
catégories FreshRSS regroupées par thématique métier, plus des catégories privées (veille
concurrentielle, à développer plus tard) ; axes de veille portés par des gabarits métier ;
régime CVE réglé dans le profil ; inscriptions ouvertes, sans validation.

La revue du 2026-11-23 a repriorisé le backlog pour une bêta : une version testable par de
premiers inscrits, pour recueillir leurs retours, avant toute préparation de l'ouverture à
l'échelle. Ce qui sert l'expérience d'un inscrit et la collecte de ses retours passe devant ;
budget, liste d'attente, parallélisme et rétention attendent. Inscription ouverte, sans plafond.
BL-071 à BL-078 en viennent, dont BL-074 à BL-076 détachés de BL-043, BL-044 et BL-066 ; BL-073
(inscription sur invitation) a été écarté avant d'être créé, son numéro reste libre de tout usage.

Les retours d'usage de la revue du 2026-11-26 donnent BL-085 à BL-096 : lecture (pagination des
résumés, animation et persistance du lecteur, journées lues, audio dans l'email), lisibilité du
profil et des catégories, charte des emails, lieu de vérité des données.
