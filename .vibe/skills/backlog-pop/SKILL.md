---
name: backlog-pop
description: Traite le ou les items suivants de backlog/todo/ — plan validé, implémentation et tests dans un worktree par item, branche poussée, item déplacé dans backlog/done/. Par priorité par défaut ; un identifiant BL-NNN force un item ; un nombre N en traite N en parallèle, de catégories différentes. Invoquée par l'utilisateur via /backlog-pop ; ne pas charger de sa propre initiative.
---

# /backlog-pop

Arguments reçus dans le message de l'utilisateur qui a invoqué `/backlog-pop`.

Tout ce que dit CLAUDE.md s'applique, à toi comme aux sous-sessions que tu lances — ce
fichier n'est pas chargé automatiquement par Vibe : le lire explicitement, avec README.md
et FONCTIONNEMENT.md. Français, unittest, Edit/Write seulement, pas de `.env`, pas de
dépendance nouvelle, conception objet sur le modèle de `llm/base.py`, pas de refactor hors
périmètre.

## 1. Lire les arguments

Dans les arguments, dans n'importe quel ordre :

- un jeton de la forme `BL-NNN` (casse indifférente) : **l'item forcé** ;
- un entier `N` (ou `-p N`, `--parallele N`) : **le nombre d'items à traiter en parallèle**,
  1 par défaut, plafonné à 4.

Tout autre jeton : s'arrêter et rappeler l'usage `/backlog-pop [BL-NNN] [N]`.

## 2. Vérifier le point de départ

- `git status` : être sur `main`, et `backlog/` sans modification non commitée — sinon s'arrêter
  et le dire : les branches partent de `HEAD`, un backlog modifié non commité ne serait pas dans
  les worktrees.
- `git fetch origin` puis vérifier que `main` n'est pas en retard sur `origin/main` ; s'il l'est,
  proposer `git pull --ff-only` avant d'aller plus loin.
- La suite doit être verte sur `main` avant de commencer (commande dans CLAUDE.md). Rouge :
  s'arrêter, ce n'est pas à un item du backlog d'en hériter.

## 3. Choisir les items

Lire les fichiers de `backlog/todo/`. Un item est un fichier `BL-NNN.md`, qui s'ouvre sur
`# BL-NNN — titre` et porte les champs **Catégorie**, **Priorité**, éventuellement **Dépend de**,
**Description**, **Bénéfice attendu**, **Tests d'acceptation**.

Éligible = catégorie différente de `exploitation`, et aucune dépendance encore présente dans
`backlog/todo/`. Ordre : priorité croissante, puis identifiant croissant.

- **Sans identifiant** : prendre les éligibles dans l'ordre, en sautant tout item dont la catégorie
  est déjà prise, jusqu'à en avoir `N`.
- **Avec identifiant** : l'item forcé d'abord, même `exploitation` ou dépendance non levée (le
  signaler alors en une ligne) ; puis compléter jusqu'à `N` comme ci-dessus, en excluant sa
  catégorie.
- Moins de `N` catégories disponibles : traiter ce qu'il y a et le dire.
- Identifiant introuvable : s'arrêter, lister les identifiants présents.

Un item `exploitation` forcé ne se code pas : livrer la procédure ou le patch documenté que décrit
l'item (dans `docs/`), et laisser l'item dans `backlog/todo/` avec une ligne « Procédure prête :
<chemin> » — il ne passe dans `backlog/done/` que quand la personne confirme l'avoir appliqué.

## 4. Planifier, puis faire valider

Pour chaque item retenu, établir un plan court : fichiers touchés (liste exacte), classes et
méthodes ajoutées ou modifiées, où vit la configuration, tests ajoutés en face de chaque test
d'acceptation, dépendance éventuelle (refusée par défaut). Avec `N > 1`, lancer une sous-session
de planification par item, toutes dans le même message.

Présenter les plans ensemble, puis demander l'accord avec l'outil `ask_user_question` — CLAUDE.md
exige l'accord au-delà de deux fichiers, et un item à moins de trois fichiers est validé dans le
même geste. Proposer : tout lancer / lancer seulement certains items / amender un plan. Un item
refusé reste dans `backlog/todo/`, intact.

Avant de lancer les sous-sessions, **réserver les identifiants** des items nouveaux que les plans
annoncent (suites, travaux hors périmètre) : le prochain libre, puis les suivants, un par item,
répartis par branche. Deux branches qui calculeraient chacune « le prochain libre » prendraient le
même numéro. Les donner dans le prompt de chaque sous-session.

## 5. Implémenter, un worktree par item

Lancer une sous-session par item validé, `placement: new_worktree`, toutes dans **un seul
message** pour qu'elles tournent en parallèle. Chaque prompt de sous-session contient, en entier
(une sous-session ne sait rien d'autre que ce que dit son prompt) :

- le texte de l'item tel qu'il figure dans `backlog/todo/BL-NNN.md` et le plan validé ;
- les consignes suivantes :
  1. Lire CLAUDE.md, README.md et FONCTIONNEMENT.md et s'y conformer (Vibe ne les charge pas
     tout seul).
  2. Renommer la branche du worktree : `git branch -m backlog/BL-NNN-<slug-court>`.
  3. Implémenter le plan, et rien d'autre. Un écart au plan nécessaire se fait et se justifie dans
     le compte rendu ; un écart de périmètre ne se fait pas.
  4. Un test dans `tests/` par test d'acceptation qui porte sur du code.
  5. Ne rien toucher dans `backlog/` : c'est le travail de l'orchestrateur.
  6. Suite complète verte (commande de CLAUDE.md), puis un ou plusieurs commits au format du dépôt
     (`feat: …`, `fix: …`, en français), avec les lignes d'attribution en vigueur.
  7. Ne pas pousser.
  8. Rendre : branche, commits, fichiers touchés, nombre de tests, chaque test d'acceptation avec
     son état (✅ / ❌ et pourquoi), écarts au plan, variables d'environnement nouvelles.

## 6. Relire

Pour chaque branche revenue verte : lancer une sous-session de revue de code (effort « medium »)
sur la branche, cible `backlog/BL-NNN-…` — lui donner le chemin de la branche à relire par rapport
à `main` et repartir de son compte rendu. Un défaut confirmé se corrige dans le worktree, suite
relancée, nouveau commit. Un item dont un test d'acceptation reste ❌ ne passe pas à l'étape 7 :
le signaler, laisser la branche et l'item en place.

## 7. Clore l'item, dans sa branche

Dans le worktree de l'item (et non sur `main` : l'item est fait quand sa branche est fusionnée,
pas avant) :

1. `git mv backlog/todo/BL-NNN.md backlog/done/BL-NNN.md`. Seul ce fichier bouge : c'est ce qui
   évite tout conflit entre branches parallèles. Ne jamais regrouper les items.
2. Dans ce fichier, ajouter après les champs d'origine :
   - `- **Réalisé le** : AAAA-MM-JJ` (date du jour) ;
   - `- **Livraison** : branche backlog/BL-NNN-…` ;
   - `- **Notes** : …` seulement s'il y a eu un écart au plan ou au texte, et pourquoi ;
   et cocher les cases des tests d'acceptation.
3. Si l'item a fait apparaître un travail nouveau hors périmètre, créer
   `backlog/todo/BL-MMM.md` avec l'identifiant **réservé** à l'étape 4 (jamais un identifiant
   recalculé ici).
4. Commit `chore(backlog): BL-NNN traité`.

## 8. Livrer

- `git push -u origin backlog/BL-NNN-…` pour chaque branche close.
- Ouvrir la PR : `gh pr create --base main` si `gh` est installé ; sinon donner le lien
  `https://github.com/odrix/RSSResume/compare/main...backlog/BL-NNN-…?expand=1`. La CI
  (`.github/workflows/tests.yml`) y lance la suite. Le corps de la PR s'écrit avec Write dans un
  fichier hors du dépôt, passé par `--body-file` : le hook `pre` refuse les heredocs et les
  redirections.
- Supprimer le worktree (`git worktree remove <chemin>`) : la branche suffit. Si Windows refuse
  (`Permission denied`), `git worktree prune` puis supprimer le dossier.

Fusionner deux PR parallèles : chaque item est son propre fichier, il n'y a pas de conflit de
backlog.

## 9. Rendre compte

Un tableau : item, branche, PR ou lien, tests (nombre total de la suite), acceptation ✅/❌.
Puis, pour chaque variable d'environnement nouvelle : la ligne exacte à coller dans `.env.local`
et ce qui reste inactif tant qu'elle n'y est pas (CLAUDE.md, « Secrets »). Enfin, l'item que
`/backlog-pop` prendrait au prochain appel.
