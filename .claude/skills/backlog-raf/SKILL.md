---
name: backlog-raf
description: Reste à faire — liste les items de backlog/todo/ par priorité (1 à 5), avec le nombre d'items par priorité, leur catégorie et ce qui les bloque. Lecture seule.
disable-model-invocation: true
---

# /backlog-raf

Le reste à faire du backlog, par priorité. **Lecture seule** : rien n'est modifié, aucune branche,
aucun agent. Le format des items est décrit dans [backlog/README.md](../../../backlog/README.md).

## 1. Lire

Avec Grep (jamais le shell), sur `backlog/todo/*.md`, en mode `content` :

- `^# BL-` : l'identifiant et le titre ;
- `^- \*\*Priorité\*\*` : la priorité ;
- `^- \*\*Catégorie\*\*` : la catégorie ;
- `^- \*\*Dépend de\*\*` : les dépendances, quand il y en a.

Les quatre résultats se recoupent par nom de fichier. Un fichier sans ligne `Priorité`, ou dont la
valeur n'est pas un entier de 1 à 5, est signalé en fin de rapport (« à corriger ») plutôt
qu'ignoré en silence.

## 2. Classer

Une dépendance est **levée** quand son `BL-NNN` n'a plus de fichier dans `backlog/todo/`. Un item est :

- **à prendre** : catégorie différente de `exploitation` et dépendances toutes levées — c'est ce
  que `/backlog-pop` peut traiter ;
- **bloqué** : au moins une dépendance encore dans `todo/` (la nommer) ;
- **à la main** : catégorie `exploitation`, jamais traitée automatiquement.

## 3. Rendre

D'abord le décompte, une ligne par priorité de 1 à 5 (les priorités vides y figurent, à 0), puis le
total :

| Priorité | Items | À prendre | Bloqués | À la main |
| --- | --- | --- | --- | --- |

Puis, par priorité croissante, la liste des items, dans l'ordre où `/backlog-pop` les prendrait
(identifiant croissant à priorité égale) :

`BL-NNN` · catégorie · titre — avec « (attend BL-MMM) » pour un item bloqué et « (à la main) »
pour `exploitation`.

Terminer par l'item que `/backlog-pop` prendrait à son prochain appel sans argument : le premier
« à prendre » de l'ordre ci-dessus.
