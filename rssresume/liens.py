"""La règle qui décide si une URL venue d'un flux peut devenir un lien.

Un module à part et non une fonction de `api/sorties.py` : l'email et le site doivent
appliquer la même règle, et `sorties.py` importe déjà la `Lettre` — la `Lettre` ne peut
donc pas l'importer en retour sans boucle.
"""

from __future__ import annotations

import urllib.parse

#: Les seuls schémas qu'un lien d'article peut porter jusqu'au lecteur.
SCHEMAS_LIENS = {"http", "https"}


def lien_sur(url: str) -> str | None:
    """L'URL si elle mène à une page web, `None` sinon.

    Les URL viennent des flux, que n'importe qui écrit : un `javascript:` posé dans un
    `href` s'exécuterait au clic, et ni Svelte ni l'échappement HTML n'assainissent un
    schéma. Chaque sortie — l'API, l'email — refait le contrôle elle-même plutôt que de
    compter sur celle d'à côté : ce qu'elle rend, elle le rend sûr.
    """
    texte = (url or "").strip()
    try:
        morceaux = urllib.parse.urlsplit(texte)
    except ValueError:
        return None
    if morceaux.scheme.lower() not in SCHEMAS_LIENS or not morceaux.netloc:
        return None
    return texte
