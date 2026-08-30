"""L'assemblage : ce qui ouvre la lettre, et les marches sur lesquelles on descend.

Deux morceaux, qui n'ont pas la même nature et ne se procurent pas de la même façon.

La **fête** vient de `fetes`, une table fixe et complète : le calendrier civil ne bouge
pas d'une année sur l'autre, et le demander à un modèle serait payer pour une donnée
qu'il peut se tromper à rendre. Elle n'a donc aucune marche à descendre.

Le **fait historique**, lui, en a trois :

1. le modèle, à qui l'on demande un événement de cybersécurité survenu à cette date, et
   à défaut un événement d'informatique — un appel par journée, pas par catégorie ;
2. la table de `histoire`, qui couvre les dates marquantes du domaine ;
3. le calendrier, qui ne se trompe jamais : rang du jour, semaine, jours restants.

Le modèle est interrogé le premier parce qu'il couvre les 365 jours ; il est aussi le
seul des trois qui puisse inventer, d'où la consigne de répondre `AUCUN` plutôt que de
combler — c'est cette réponse-là qui fait descendre à la table.
"""

from __future__ import annotations

import datetime as dt

from rssresume.ephemeride import fetes, histoire
from rssresume.models import Ephemeride
from rssresume.tools import console

#: Ce que le modèle répond quand il ne connaît aucun événement à cette date. Comparé
#: après repli de casse et sans ponctuation finale : un modèle ajoute volontiers un point.
AUCUNE = "aucun"

#: Longueur au-delà de laquelle la réponse n'est plus une éphéméride mais un paragraphe.
#: Le modèle qui déborde n'est pas repris — on garde la table, qui tient en une ligne.
LONGUEUR_MAX = 400


class EphemerideService:
    """Rend l'éphéméride d'une journée, avec ou sans fournisseur.

    Sans fournisseur — aucune clé d'API pour cette action — le service ne tombe pas en
    panne : il descend d'un cran, comme il le fait déjà quand le modèle ne sait rien
    dire de cette date. L'email a toujours son introduction.
    """

    def __init__(self, provider=None):
        #: `None` quand la clé manque. Le repli n'est pas un cas dégradé, c'est un mode.
        self._provider = provider

    def of(self, day: dt.date) -> Ephemeride:
        """L'éphéméride du jour de l'envoi : sa fête, et le fait que l'on sait de cette date.

        `day` est le jour de l'ENVOI. L'appelant qui lui passerait la journée digérée
        obtiendrait une lettre datée de la veille — c'est précisément le défaut que
        cette signature rend visible.
        """
        return self._du_modele(day) or table(day) or calendrier(day)

    def _du_modele(self, day: dt.date) -> Ephemeride | None:
        """Ce que le modèle sait de cette date, `None` s'il ne sait rien ou s'il échoue.

        L'échec est rattrapé et non propagé : une éphéméride est un ornement, et perdre
        la journée entière — scoring, résumés, synthèse vocale — pour une phrase
        d'introduction serait hors de proportion.
        """
        if self._provider is None:
            return None
        try:
            texte = (self._provider.write_ephemeride(day) or "").strip()
        except Exception as exc:  # un fournisseur a mille façons d'échouer, aucune fatale
            console.detail(f"éphéméride : {exc}, repli sur la table embarquée")
            return None
        if not texte or texte.rstrip(" .").casefold() == AUCUNE or len(texte) > LONGUEUR_MAX:
            console.detail("éphéméride : le modèle n'a rien retenu pour cette date")
            return None
        console.detail(f"éphéméride : {texte}")
        return _batir(day, texte, "llm")


def table(day: dt.date) -> Ephemeride | None:
    """L'entrée de la table embarquée pour cette date, `None` s'il n'y en a pas."""
    texte = histoire.du_jour(day)
    return _batir(day, texte, "table") if texte else None


def calendrier(day: dt.date) -> Ephemeride:
    """Le repli qui ne peut pas échouer : ce que la date dit d'elle-même.

    Sans intérêt historique, mais jamais faux et jamais vide — et c'est tout ce qu'on
    demande à la dernière marche. La fête, elle, reste celle du jour : elle vient d'une
    table complète, et n'a donc pas de marche à descendre.
    """
    # « 1er jour », et non « 1e » : le premier rang s'écrit à part, en français.
    rang = day.timetuple().tm_yday
    rang_ecrit = "1er" if rang == 1 else f"{rang}e"
    restants = dt.date(day.year, 12, 31).toordinal() - day.toordinal()
    semaine = day.isocalendar().week
    pluriel = "s" if restants > 1 else ""
    return _batir(
        day,
        f"{rang_ecrit} jour de l'année, semaine {semaine}. "
        f"{restants} jour{pluriel} avant la fin de l'année.",
        "calendrier",
    )


def pour_envoi(relue: Ephemeride | None, envoi: dt.date) -> Ephemeride:
    """L'éphéméride à mettre dans une lettre renvoyée, sans rappeler le moindre modèle.

    Celle du journal ne sert que si elle parle bien du jour où l'on renvoie — le cas
    courant : l'envoi a échoué ce matin, on relance une heure plus tard. Renvoyée
    trois jours après, elle daterait la lettre du mauvais jour et annoncerait la fête
    d'un autre : on recalcule alors sur la table et le calendrier, qui ne coûtent rien.
    """
    if relue is not None and relue.jour == envoi:
        return relue
    return EphemerideService().of(envoi)


def _batir(day: dt.date, texte: str, origine: str) -> Ephemeride:
    """Assemble l'éphéméride. La fête est jointe ici, quelle que soit l'origine du fait.

    Un seul endroit la pose : les trois sources rendaient sinon trois objets dont l'une
    aurait fini par oublier la fête, et le défaut ne se verrait qu'un matin sur trois.
    """
    return Ephemeride(jour=day, fete=fetes.du_jour(day), texte=texte, origine=origine)
