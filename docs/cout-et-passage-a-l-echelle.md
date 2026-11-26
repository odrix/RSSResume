# Coût et passage à l'échelle - combien coûte un inscrit

Étude BL-052, **mesurée en septembre 2026, sur un profil**. L'inscription est ouverte : chaque
profil note tous les articles de ses catégories, se fait résumer les siens, monter et lire sa
journée. Ce document chiffre ce qu'un profil coûte, ce qui casse avant la facture, et dans quel
ordre agir.

Les chiffres datent de deux mois avant l'étude (rédigée le 2026-11-22) : les prompts, le montage
et les axes de veille ont bougé depuis. Ils fixent les ordres de grandeur et l'ordre d'action ; le
budget de BL-057 se règle sur une mesure refaite (BL-061), pas sur eux.

## 1. En bref

- Un profil coûte **0,17 $ par jour** en moyenne (0,19 $ un jour de semaine), soit **~5 $ par mois**,
  si `gpt-5.6-luna` est facturé comme `gpt-5` ; **0,09 $/jour, ~2,7 $/mois** au tarif de `gpt-5-mini`.
  Son vrai tarif manque à la grille : c'est le premier chiffre à obtenir (BL-055).
- La facture n'est **pas** le scoring (2 %) : c'est la synthèse vocale (41 %), le résumé (32 %) et
  le montage (23 %). Mutualiser la notation n'économise presque rien.
- BL-038 (abonnements) ramène un profil métier à **0,11-0,12 $ par jour de semaine** : un socle
  de ~0,06 $ (montage, voix, éphéméride) que rien ne réduit, plus ~0,06 $ par catégorie active.
- Ce qui casse en premier n'est pas l'argent : ce sont les **libellés FreshRSS**, au moins 18 par
  profil. Dès 3 à 5 profils la barre latérale est illisible : le cache de scoring doit sortir vers
  SQLite **avant l'ouverture** (BL-056).
- Recommandation : cache SQLite et plafond de profils avec budget journalier avant d'ouvrir ;
  l'audio à la demande vers 20-30 profils ; la tournée parallèle et la rétention vers 40-50.

## 2. Sources et méthode

| | |
| --- | --- |
| Données | `output-dl/2026-08-27 … 2026-09-18/` : copie locale du répertoire `output/` du VPS (production, passage de 05:00, un profil, toutes les catégories, disposition à plat). `output/` désigne ci-dessous le répertoire de sortie local, celui des essais |
| Champs lus | `<categorie>.log.json` : `couts.appels[]` (`typologie`, `modele`, `tokens_entree`, `tokens_sortie`), `resultat.articles`, `retenus`, `notes_calculees`, `notes_relues_des_tags`, `genere_le` ; `journee.json` : éphéméride, montage, TTS (`caracteres`) |
| Tarifs | `llm/providers.json`, bloc `prices`, appliqué comme [`pricing.py`](../rssresume/pricing.py) : `tokens_entree × input + tokens_sortie × output`. `tokens_sortie` est le `completion_tokens` de l'API, raisonnement **compris** |
| Régime mesuré | **2026-09-07 → 2026-09-18**, dix journées (8 de semaine, 2 de week-end ; le 16 et le 17 manquent) |

Pièges, et ce qui en a été fait :

1. **`gpt-5.6-luna` n'a pas de tarif** dans la grille : son `cout` vaut `null` dans tous les
   journaux, et `pricing.tarif` refuse à raison de le rattacher à `gpt-5`. Tout coût qui le
   concerne est donné entre deux bornes lues dans `providers.json` : **haute** au tarif `gpt-5`
   (1,25 $ / 10 $ par million de tokens), **basse** au tarif `gpt-5-mini` (0,25 $ / 2 $). Le vrai
   tarif est à fournir.
2. **Un rejeu écrase le journal** : la journée locale `output/2026-08-28` relancée à 20:43 dit `notes_calculees 0`,
   `relues 32`, et ne compte plus le scoring. Seules sont gardées les journées où
   `notes_calculees = articles` pour chaque catégorie notée ; `2026-08-27` (partielle) est écartée.
3. **Le montage lit le texte des articles depuis le 2026-09-07** : 10 à 23 k tokens d'entrée en
   semaine, contre 3 à 5 k avant. Le régime actuel se mesure donc à partir de cette date.
4. **Semaine et week-end** n'ont rien à voir : 66-96 articles notés un jour de semaine, 14-16 le
   week-end. Les deux sont donnés.
5. **Un seul profil, arrêté au 2026-09-18.** Pour rejouer l'étude : rapatrier du VPS
   (répertoire de sortie du conteneur) `output/<id>/<date>/` de chaque profil sur deux semaines, et appliquer les mêmes filtres -
   ou, une fois BL-061 fait, `--couts`.

## 3. Coût mesuré

### Par poste, par profil et par jour

| Poste | Modèle | Moyenne haute | Part | Moyenne basse | Part |
| --- | --- | ---: | ---: | ---: | ---: |
| Scoring | gpt-4o-mini (tarifé) | 0,0035 $ | 2 % | 0,0035 $ | 4 % |
| Résumé de catégorie | luna | 0,0530 $ | 32 % | 0,0106 $ | 12 % |
| Montage de la journée | luna | 0,0378 $ | 23 % | 0,0076 $ | 8 % |
| Synthèse vocale | voxtral-mini-tts (tarifé, 16 $/M car.) | 0,0686 $ | 41 % | 0,0686 $ | 76 % |
| Éphéméride | luna | 0,0031 $ | 2 % | 0,0006 $ | 1 % |
| **Total** | | **0,166 $** | | **0,091 $** | |

### Semaine et week-end

| | Articles notés | Retenus | Caractères lus | Total haut | Total bas |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jour de semaine (8 j.) | 79,5 (66-96) | 24,6 | 4 775 | **0,187 $** | **0,102 $** |
| Week-end (2 j.) | 15 | 2,5 | 2 346 | 0,081 $ | 0,047 $ |
| Moyenne (10 j.) | 66,6 | 20,2 | 4 289 | 0,166 $ | 0,091 $ |

Avant le 2026-09-07 (montage plus court, audio plus long), la moyenne était de 0,196 $ / 0,132 $ :
la voix pesait 57 %, à 7 000 caractères par jour.

### Coûts unitaires (régressions sur le régime actuel)

| Unité | Borne haute | Borne basse |
| --- | ---: | ---: |
| Article noté | 5,2 × 10⁻⁵ $ | 5,2 × 10⁻⁵ $ |
| Catégorie résumée (fixe) | 0,0074 $ | 0,0015 $ |
| Article retenu, au résumé | 0,0018 $ | 0,0004 $ |
| Montage (fixe) | 0,018 $ | 0,004 $ |
| Article retenu, au montage | 0,0010 $ | 0,0002 $ |
| Caractères de voix | ~2 300 + 100 par retenu, à 16 $/M | idem |

### Par catégorie (moyenne des jours où elle a des articles, borne haute)

| Catégorie | Articles | Retenus | Coût hors montage et voix |
| --- | ---: | ---: | ---: |
| Cybersécurité technique et menaces | 26,3 | 10,1 | 0,028 $ |
| Tech généraliste | 34,1 | 8,0 | 0,022 $ |
| Concurrence EFSS et MFT | 4,2 | 2,0 | 0,007 $ |
| Alertes CERT-FR / ANSSI | 8,2 | 0,5 | 0 $ (déterministe) |
| Optionnel, conformité, cloud souverain, side business | 1-3 | ~0 | < 0,001 $ |

### Partagé ou payé par profil

| Partagé par la tournée | Payé par chaque profil |
| --- | --- |
| La lecture FreshRSS : une par catégorie et par tournée (`_Session`) | Le scoring de tous les articles de ses catégories |
| Le marquage comme lu | Les résumés, le montage, la synthèse vocale |
| CERT-FR : déterministe, aucun appel | L'**éphéméride** : `cli.build_service` crée un `EphemerideService` par profil, donc un appel par profil |

## 4. Modèle de coût et effet de BL-038

```
c(profil, jour) = Σ_{cat suivies} [ 5,2e-5 × articles_cat + résumé(retenus_cat) ]
                + montage(Σ retenus) + voix(Σ retenus) + éphéméride
```

Le modèle redonne 0,192 $ pour le profil actuel un jour de semaine, contre 0,187 $ mesuré.

| Profil (jour de semaine) | Catégories | Retenus | Haut | Bas |
| --- | --- | ---: | ---: | ---: |
| **Avant BL-038** : tout profil | toutes | 24,6 | **0,19 $** | **0,10 $** |
| CTO (après BL-038) | toutes | 24,6 | 0,19 $ | 0,10 $ |
| RSSI | cyber + conformité + CERT-FR | 12,5 | 0,12 $ | 0,07 $ |
| Développeur | tech généraliste + dev | 10 | 0,11 $ | 0,07 $ |
| Designer | tech généraliste | 10 | 0,11 $ | 0,07 $ |
| Catalogue ×3 (BL-050/051), CTO | toutes | 31 (plafond 12 par catégorie) | 0,23 $ | 0,13 $ |
| Catalogue ×3, profil métier | une ou deux | 12 | 0,12 $ | 0,08 $ |

Lecture : un profil coûte **~0,06 $ de socle** (montage fixe, ~2 300 caractères de voix,
éphéméride) **plus ~0,06 $ par catégorie active saturée** (borne haute). Le plafond de 12 retenus
par catégorie borne la facture : tripler le catalogue ne triple que le scoring, qui ne pèse rien.
BL-038 fait gagner ~40 % sur un profil étroit, pas davantage, parce que le socle reste.

À l'échelle, en moyenne mensuelle (borne haute / basse) :

| Profils | Avant BL-038 | Après BL-038, profils métier |
| ---: | ---: | ---: |
| 10 | 50 $ / 27 $ | 28 $ / 17 $ |
| 30 | 150 $ / 82 $ | 84 $ / 50 $ |
| 50 | 250 $ / 137 $ | 140 $ / 84 $ |
| 100 | 500 $ / 273 $ | 280 $ / 168 $ |

## 5. Libellés FreshRSS

Vérifié dans [`external/freshrss.py`](../rssresume/external/freshrss.py) (`Etiquettes`,
`tag_notes`, `clear_scoring_tags`, `mark_digested`). Tous sont préfixés du nom de la personne
(`adrien-score-07`) et vivent dans le FreshRSS **partagé**.

| Libellé | Par profil |
| --- | --- |
| `<p>-score-00` … `<p>-score-10` | 11 |
| `<p>-theme-*` | 5 (3 à 6 par jeu d'axes après BL-039, un jeu de plus à chaque changement d'axes) |
| `<p>-scoring-<hash>` | 1 courant **+ 1 par version passée** |
| `<p>-digested` | 1 |
| **Total** | **≥ 18, + 1 à chaque édition du profil** |

- L'empreinte hache `scoring_system(profil)` et le modèle : **chaque édition du texte du profil**
  crée un libellé, et un changement du prompt de scoring en crée un pour chaque profil.
- `clear_scoring_tags` retire les libellés **des articles** (`edit-tag` avec `r`) ; aucun
  `disable-tag` ne supprime le libellé lui-même. Ils s'accumulent (c'est BL-025).
- Écritures : `tag_notes` fait un `edit-tag` par valeur de score et par thème, plus l'empreinte,
  puis `mark_digested` : **7 appels par catégorie et par profil en moyenne, 12 sur une grosse
  catégorie, 15 au plus**, 30 à 50 par profil et par jour.

À 3 profils : 54 libellés ; à 30 : plus de 540. Au-delà de quelques profils, la barre latérale de
FreshRSS ne sert plus à rien à l'administrateur, et les tags ne disent rien qu'un lecteur humain
utilise : ils ne sont qu'un cache.

## 6. Autres limites

| Limite | Mesure | Où elle casse |
| --- | --- | --- |
| Durée | 104-149 s par profil un jour de semaine (écart de `genere_le` à 05:00), 48-63 s le week-end ; tournée **séquentielle** | Fenêtre de 2 h : ~50 profils au pire jour mesuré, davantage avec des profils étroits |
| Disque | 1,9 Mo par jour et par profil (mp3 à 96 %), 2,1 Mo en semaine | 0,7 Go par an et par profil : **35 Go/an à 50 profils** |
| Email | un envoi par profil et par jour ; `journee.mp3` de 0,8 à 2,7 Mo en pièce jointe | Quota journalier et mensuel de Resend, et taille des pièces jointes : **à vérifier** sur l'offre souscrite (non consulté ici) |
| Appels FreshRSS | 30-50 `edit-tag` par profil et par jour | Supportable, mais disparaît avec le cache SQLite |

## 7. Options comparées

| | Option | Gain | Effort | Risque | Devient nécessaire |
| --- | --- | --- | --- | --- | --- |
| A | **Plafond de profils servis + budget journalier** de la tournée (`N_max = budget / c`) | Borne la facture, quel que soit le nombre d'inscrits | Faible | Exige le tarif de luna, sinon le budget est aveugle | **Dès l'ouverture** |
| B | Scoring mutualisé par gabarit (une note par gabarit et par article) | ≤ 2 % du coût (0,0035 $/profil/jour) | Moyen | Contredit BL-041 : le gabarit pré-remplit, il n'y reste pas lié, dès la première retouche, la note n'est plus celle de la personne | **Non retenue.** À revoir si le scoring dépasse 20 % du coût, soit ~600 articles notés par profil et par jour |
| C | **Cache de scoring en SQLite**, clé `(item_id, empreinte)` → note, thème, angle | Plus aucun libellé ni `edit-tag` de notation ; l'angle est enfin persisté ; deux profils au texte identique partagent la même empreinte, donc le bénéfice de B gratuitement | Moyen (la base existe : `annuaire_sqlite.py`) | Migration : les notes des tags sont perdues une fois, d'où une journée renotée (~0,004 $/profil) | **Dès 3-5 profils**, donc avant l'ouverture |
| D | Éphéméride une fois par tournée | 0,003 $/profil/jour (haut) | Très faible | Aucun tant que l'éphéméride n'est pas personnelle (BL-042) | Maintenant, au passage |
| E | Audio de journée en option ou à la demande | 41 % (haut) à 76 % (bas) du coût d'un profil qui n'écoute pas | Moyen ; s'appuie sur le lien audio de BL-044 | Latence à la première écoute si synthèse à la demande | **Vers 20-30 profils**, ou au premier dépassement du budget |
| F | Tournée en parallèle | Divise la durée | Élevé : `runlog` tient le journal actif dans un état de module (`_actif`), à rendre local | Limites de débit des fournisseurs | **Vers 40-50 profils** (fenêtre de 2 h) |
| G | Rétention des sorties par profil (mp3 purgés après N jours, journaux gardés) | 96 % du disque | Faible | Le site ne rejoue plus un vieil audio | **Vers 30-50 profils**, selon le disque du VPS |

## 8. Recommandation et seuils de bascule

| À … | Faire |
| --- | --- |
| **Maintenant** | Tarifer `gpt-5.6-luna` (BL-055) : sans lui, aucun budget n'est calculable. Mesurer par profil (BL-061). Éphéméride une fois par tournée (BL-059), au passage |
| **Avant l'ouverture** (3-5 profils) | Cache de scoring en SQLite (BL-056), puis ménage des libellés existants (BL-025). Plafond de profils et budget journalier (BL-057), et l'inscription qui se ferme ou passe en liste d'attente au plafond (BL-058) |
| **20-30 profils** (borne haute : 100 à 150 $/mois avant BL-038, 56 à 84 $ après) | Audio en option ou à la demande (BL-060) |
| **40-50 profils** | Tournée en parallèle (BL-062) quand la tournée dépasse sa fenêtre ; rétention des sorties (BL-063) quand le disque l'exige |
| **Jamais, dans cet horizon** | Scoring mutualisé par gabarit (B) |

Ordre de grandeur pour régler le plafond, en borne haute : **un budget de 1 $ par jour sert
5 profils « tout » ou 8 à 9 profils métier** ; au tarif `gpt-5-mini`, 10 et 12 à 14.

## 9. Items créés

| Item | Titre | Catégorie | Priorité | Dépend de |
| --- | --- | --- | --- | --- |
| BL-055 | Tarifer `gpt-5.6-luna` dans la grille livrée | prompts | 1 | |
| BL-056 | Cache de scoring en SQLite, hors des libellés FreshRSS | pipeline | 1 | |
| BL-057 | Plafond de profils servis et budget journalier de la tournée | pipeline | 1 | BL-055 |
| BL-058 | Inscription fermée ou liste d'attente au plafond | web | 2 | BL-057 |
| BL-059 | Éphéméride calculée une fois par tournée | pipeline | 3 | |
| BL-060 | Audio de journée en option ou à la demande | pipeline | 2 | BL-044 |
| BL-061 | Bilan de coût par profil sur une période, option CLI `--couts` | cli | 2 | |
| BL-062 | Tournée en parallèle | pipeline | 4 | |
| BL-063 | Rétention des sorties par profil | pipeline | 4 | |

BL-054 est pris par un autre item ouvert le même jour. Ajustements appliqués au backlog : BL-025
dépend de BL-056, s'étend aux libellés `score`, `theme` et `scoring` de tous les profils, et passe
de la priorité 4 à 2. BL-049 (coût des sept derniers jours à l'admin) pourra s'appuyer sur BL-055
et BL-061, sans en dépendre : la suspension et la suppression de compte n'en ont pas besoin.
