# Prompt de scoring — ce qui part vers OpenAI

Ce qu'un appel de **notation** envoie, mot pour mot. Le code de référence est
[`processing.py`](../rssresume/processing.py) (`scoring_system`, `_score_batch`).

## Convention de lecture

Tout ce qui suit est envoyé **littéralement**, sauf les `{accolades}` : ce sont les données
injectées à l'exécution. Chacune est décrite dans le tableau [Données injectées](#données-injectées).

## En un coup d'œil

| | |
| --- | --- |
| Endpoint | `POST {OPENAI_BASE_URL}/chat/completions` |
| Modèle | `OPENAI_SCORING_MODEL`, défaut `gpt-4o-mini` — lu **à l'import** de `llm.py`, pas depuis `AppConfig` |
| Paramètres | `temperature: 0.1`, `max_tokens: 4096` (modèle classique) |
| Fréquence | **un appel par lot de 40 articles à noter** (`SCORING_BATCH_SIZE`), par catégorie |
| Ce qu'il voit | titre + 400 caractères, pour **tous** les articles du jour |
| Ordre de grandeur réel | ~2 950 tokens d'entrée / ~860 de sortie pour 19 articles |

Le modèle reste volontairement classique : la notation est un tri sur barème, pas un
raisonnement — et changer ce modèle change l'empreinte du prompt, donc renote tout l'historique.

---

## Message `system`

```text
Tu assistes la veille quotidienne de la personne dont voici le profil. Ce profil est le SEUL critère de pertinence :

{profil}

Tu reçois une liste d'articles (id, titre, résumé court). Pour CHAQUE article tu produis :
- "score" : entier de 0 à 10 selon le barème ci-dessous ;
- "thematique" : exactement une valeur parmi reglementaire, cyber, marche, stack, autre ;
- "angle" : UNE phrase expliquant en quoi l'article compte (ou non) pour ce profil précis.

Barème :
0-2  hors sujet pour ce profil
3-4  connexe, mais sans conséquence pour ce profil
5-6  intéressant à connaître, non actionnable
7-8  pertinent, à lire aujourd'hui
9-10 critique ou directement actionnable (obligation à respecter, faille sur ses propres
     outils, mouvement d'un concurrent direct)

Règles impératives :
- Traite TOUS les articles reçus, sans exception ni échantillonnage. Un article hors sujet
  reçoit un score bas, il n'est jamais omis.
- Renvoie exactement autant d'objets que d'articles reçus, dans le même ordre, en reprenant
  l'id d'origine à l'identique.
- Un résumé vide n'est pas une raison d'omettre l'article : juge alors sur le seul titre.
- Réponds UNIQUEMENT par du JSON valide, sans texte avant ni après, sans balises Markdown.

Format JSON exact attendu :
{"resultats": [{"id": "...", "score": 0, "thematique": "...", "angle": "..."}]}
```

> Les deux dernières lignes contiennent de vraies accolades : ce sont le format JSON attendu,
> pas des données injectées. C'est aussi la raison pour laquelle le prompt est assemblé par
> **concaténation et jamais par `format()`** — un profil venu de l'extérieur peut lui aussi
> contenir des accolades.

---

## Message `user`

```text
{nombre d'articles du lot} articles à évaluer :

[{"id": "{rang}", "titre": "{titre de l'article}", "resume": "{400 premiers caractères du texte de l'article}"}, …]
```

Le JSON est sur une seule ligne, sans indentation, `ensure_ascii=False` (les accents partent tels
quels et non en `é`).

---

## Données injectées

| Motif | Source dans le code | Transformation |
| --- | --- | --- |
| `{profil}` | `profil.load_profil()` | `RSSRESUME_PROFILE` > `RSSRESUME_PROFILE_FILE` > `DEFAULT_PROFIL`. Inséré tel quel |
| `{nombre d'articles du lot}` | `len(payload)` | 40 au maximum ; c'est le nombre d'articles **du lot**, pas de la catégorie |
| `{rang}` | position dans le lot | `"1"`, `"2"`… **jamais l'`item_id` FreshRSS** : une chaîne comme `tag:google.com,2005:reader/item/000659ce0338ac4f` revenait recopiée de travers assez souvent pour faire échouer tout le lot |
| `{titre de l'article}` | `Article.title` | brut |
| `{400 premiers caractères du texte de l'article}` | `Article.content_text[:400]` | HTML déjà retiré (`strip_html`), coupé à `SCORING_EXCERPT_LENGTH = 400` caractères, sans respect des mots. Vide → remplacé par la chaîne littérale `(aucun résumé fourni)` |

### Ce qui n'est **pas** envoyé

L'URL, le nom du flux, la date de publication, l'`item_id` FreshRSS, et le texte intégral.
`digest._to_payload` prépare bien `source` et `url`, mais `_score_batch` ne les recopie pas dans
le message : le scoring est une étape de tri, pas de compréhension, et chaque champ inutile est
payé sur 40 articles à la fois.

---

## Exemple rempli

Deux articles, profil par défaut. Message `user` réellement envoyé :

```text
2 articles à évaluer :

[{"id": "1", "titre": "L'ANSSI publie la version 3.3 du référentiel SecNumCloud", "resume": "Le référentiel SecNumCloud évolue avec de nouvelles exigences sur la localisation des données et l'immunité aux législations extraterritoriales. Les prestataires qualifiés disposent de dix-huit mois pour se mettre en conf"}, {"id": "2", "titre": "CVE-2026-0000 : exécution de code à distance dans une librairie de chiffrement", "resume": "(aucun résumé fourni)"}]
```

Réponse attendue :

```json
{"resultats": [
  {"id": "1", "score": 9, "thematique": "reglementaire", "angle": "Dix-huit mois pour se remettre en conformité sur un référentiel dont dépend sa qualification."},
  {"id": "2", "score": 8, "thematique": "cyber", "angle": "Une RCE dans une librairie de chiffrement touche directement une chaîne de traitement de fichiers."}
]}
```

Ce que devient chaque champ de la réponse :

| Champ | Où il sert ensuite |
| --- | --- |
| `score` | seuil de sélection, plafond, tag FreshRSS `score-NN`, bloc `articles` du journal |
| `thematique` | ordre de lecture du digest, tag `theme-<x>`, envoyé au [prompt de résumé](prompt-resume.md) |
| `angle` | envoyé au [prompt de résumé](prompt-resume.md). **Non persisté** dans FreshRSS — une phrase entière n'est pas un tag — donc une note relue du cache revient sans son angle |

---

## Ce qui déclenche un nouvel appel

Une empreinte SHA-256 de `scoring_system(profil) + llm.SCORING.model`, tronquée à 12 caractères,
est écrite sur chaque article en tag `scoring-<hash>`. Tant qu'elle ne bouge pas, l'article n'est
pas renoté et **aucun appel n'est fait**.

Changent l'empreinte, donc renotent tout l'historique : le profil, le barème, les règles
ci-dessus, `SCORING_INTRO`, ou `OPENAI_SCORING_MODEL`.

Ne la changent pas : le seuil — général, propre à une catégorie ou abaissé par le repli —, le plafond, et tout le prompt de résumé.
