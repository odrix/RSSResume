"""Journal d'exécution : un fichier `<catégorie>.log.json` par catégorie et par jour.

Ce que les appels IA coûtent n'est nulle part une fois l'exécution finie. Le journal
le fixe, catégorie par catégorie, à côté de l'audio du jour :

- les articles lus et ce que le scoring en a fait (score, thématique, angle, retenu
  ou non, note calculée ou relue des tags) ;
- le coût des appels IA, détaillé par typologie — la somme des scorings, celle des
  résumés, celle de la synthèse vocale — et le détail appel par appel.

Une catégorie sans article du jour n'écrit aucun journal : elle ne lit rien, ne note
rien et ne dépense rien, et son marqueur `.no-article` dit déjà tout ce qu'il y a à dire.

À côté d'eux, un `journee.json` porte ce qui n'appartient à aucune catégorie : l'
éphéméride qui ouvre l'email, et l'appel qui l'a produite. Lui aussi n'est écrit que
s'il a quelque chose à transporter.

Le journal actif est un état de module : les appels partent du fond d'un `LLMProvider`,
qui n'a aucune raison de savoir quelle catégorie est en cours. Le
pipeline est séquentiel — une catégorie à la fois — et ce module l'est donc aussi.
Hors de tout `category_scope`, tout enregistrement est un no-op : `llm/processing.py`
lancé seul et les tests n'écrivent rien.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import json
import pathlib
from typing import Any, Iterator

from rssresume import pricing
from rssresume.models import (
    WATCHLIST_MAX,
    WATCHLIST_MIN,
    Article,
    CategoryDigest,
    Ephemeride,
    Note,
)

#: Extension du journal, à côté du `.mp3` ou du `.no-article` de la même catégorie.
LOG_SUFFIX = ".log.json"

#: Le journal de la journée, à côté de ceux des catégories. Sans le suffixe `.log.json`,
#: et c'est délibéré : `read_day` ramasse les journaux de catégorie au glob, et un
#: fichier de journée qui répondrait au même motif se relirait comme une catégorie vide.
DAY_LOG_NAME = "journee.json"

#: Les postes de dépense, dans l'ordre où ils sont engagés. L'éphéméride est le seul
#: qui ne soit pas payé par catégorie : un appel pour la journée entière, et il apparaît
#: donc dans le journal de la journée, jamais dans celui d'une catégorie.
TYPOLOGIES = ("scoring", "resume", "ephemeride", "tts")

#: Action (au sens de `providers.ACTIONS`) rangée sous son poste de dépense. Le résumé
#: par article et le digest de catégorie sont deux façons de résumer : même poste.
TYPOLOGIE_PAR_LABEL = {
    "scoring": "scoring",
    "article": "resume",
    "digest": "resume",
    "ephemeride": "ephemeride",
    "tts": "tts",
}
TYPOLOGIE_PAR_DEFAUT = "resume"

#: Comment chaque poste se dit dans le récapitulatif de fin d'exécution. Les clés JSON
#: restent sans accent — elles sont relues par des outils — mais la console s'adresse à
#: quelqu'un, et « tts » ne dit rien à qui lit son digest du matin.
LIBELLE_TYPOLOGIE = {
    "scoring": "scoring",
    "resume": "résumé",
    "ephemeride": "éphéméride",
    "tts": "synthèse vocale",
}

#: Ouverture du récapitulatif, dans le style des autres lignes de la console.
RECAP_PREFIXE = "Consommation IA"


def read_day(day_dir: pathlib.Path) -> list[CategoryDigest]:
    """Les digests d'une journée, relus de ses journaux.

    De quoi renvoyer l'email d'une journée déjà produite sans rappeler ni FreshRSS ni le
    moindre fournisseur : tout ce que l'email porte — le résumé, les liens des articles
    retenus, le nom de l'audio — est déjà sur le disque.

    L'ordre est celui des noms de fichier, donc celui des catégories quand elles sont
    numérotées comme FreshRSS invite à le faire. `articles` reste vide : la relecture ne
    sert qu'à écrire un email, et surtout pas à remarquer des articles comme lus.

    Une catégorie sans le moindre article n'a pas de journal — elle n'a rien lu ni rien
    dépensé — et manque donc à la relecture, avec sa ligne « aucun article » dans le corps.
    """
    if not day_dir.is_dir():
        return []
    return [
        _digest_relu(json.loads(path.read_text(encoding="utf-8")), day_dir)
        for path in sorted(day_dir.glob(f"*{LOG_SUFFIX}"))
    ]


def _digest_relu(journal: dict, day_dir: pathlib.Path) -> CategoryDigest:
    audio = (journal.get("resultat") or {}).get("audio")
    chemin = day_dir / audio if audio else None
    return CategoryDigest(
        category=journal.get("categorie") or "",
        articles=[],
        summary_text=journal.get("resume") or "",
        selected=[_article_relu(entree, journal) for entree in _retenus(journal)],
        watchlist=[_article_relu(entree, journal) for entree in _a_surveiller(journal)],
        # Un journal peut nommer un audio que l'on a supprimé depuis : l'email part
        # alors sans lui plutôt que d'échouer à la lecture d'un fichier absent.
        audio_path=chemin if chemin and chemin.is_file() else None,
    )


def _retenus(journal: dict) -> list[dict]:
    """Les articles retenus, dans l'ordre où le résumé les a racontés."""
    retenus = [entree for entree in journal.get("articles") or [] if entree.get("retenu")]
    return sorted(retenus, key=lambda entree: entree.get("rang_digest") or 0)


def _a_surveiller(journal: dict) -> list[dict]:
    """Les articles de la liste de veille, les mieux notés en tête.

    Recalculés du journal plutôt que stockés à côté : le score de chaque article y est
    déjà, et la fourchette est une règle d'affichage. Un journal écrit avant cette
    règle se relit donc avec sa liste de veille, sans avoir rien à convertir — et
    changer la fourchette n'oblige pas à réécrire les journées passées.
    """
    candidats = [
        entree
        for entree in journal.get("articles") or []
        if not entree.get("retenu")
        and isinstance(entree.get("score"), int)
        and WATCHLIST_MIN <= entree["score"] <= WATCHLIST_MAX
    ]
    return sorted(candidats, key=lambda entree: entree["score"], reverse=True)


def _article_relu(entree: dict, journal: dict) -> Article:
    """L'article réduit à ce que l'email en montre : son titre, son flux, son URL."""
    return Article(
        item_id=entree.get("item_id") or "",
        category=journal.get("categorie") or "",
        title=entree.get("titre") or "",
        url=entree.get("url") or "",
        published_at=_publie_le(entree.get("publie_le"), journal.get("date")),
        feed_title=entree.get("flux") or "",
        content_text="",
    )


def _publie_le(horodatage: str | None, jour: str | None) -> dt.datetime:
    """L'heure de publication, ou le début de la journée à défaut.

    Le champ est requis par `Article` mais ne part pas dans l'email : une date approchée
    vaut mieux qu'une relecture qui échoue sur un article dont le flux datait mal.
    """
    for valeur in (horodatage, jour):
        try:
            return dt.datetime.fromisoformat(valeur)
        except (TypeError, ValueError):
            continue
    return dt.datetime.min


@dataclasses.dataclass
class Call:
    """Un appel au fournisseur, avec ce qu'il a consommé et ce qu'il a coûté."""

    typologie: str
    #: L'action appelée : scoring, article, digest, tts.
    label: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    #: Inclus dans `output_tokens`, isolé ici : c'est lui qui explique une facture
    #: de digest sans rapport avec la longueur du texte rendu.
    reasoning_tokens: int = 0
    #: Synthèse vocale seulement : le texte envoyé, à la source de la facturation.
    characters: int = 0
    #: `None` quand le modèle n'est pas dans la grille de `pricing.py`.
    cost: float | None = None
    #: Vrai quand le coût repose sur une estimation tokens/caractères (TTS).
    estimated: bool = False
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)

    def as_json(self) -> dict:
        entree = {
            "typologie": self.typologie,
            "type_appel": self.label,
            "modele": self.model,
            "tokens_entree": self.input_tokens,
            "tokens_sortie": self.output_tokens,
            "tokens_raisonnement": self.reasoning_tokens,
            "cout": _round(self.cost),
        }
        if self.characters:
            entree["caracteres"] = self.characters
        if self.estimated:
            entree["cout_estime"] = True
        entree.update(self.detail)
        return entree


class Comptes:
    """La table de coûts d'un ensemble d'appels, d'où qu'ils viennent.

    Sortie du `Journal` le jour où la journée entière a eu besoin d'être totalisée : la
    somme des catégories ne s'écrit dans aucun fichier — chacune a déjà le sien — et
    n'appartient donc à aucun journal. La compter ailleurs aurait fait deux additions
    qui finissent par ne plus donner le même chiffre, et c'est précisément le genre de
    divergence que personne ne remarque.

    La même table sert donc au bloc `couts` d'un journal (`as_json`) et au récapitulatif
    affiché en fin d'exécution (`texte`).
    """

    def __init__(self, calls: list[Call]):
        self.calls = calls

    @property
    def devise(self) -> str:
        return pricing.CURRENCY

    @property
    def modeles_sans_tarif(self) -> list[str]:
        return sorted({call.model for call in self.calls if call.cost is None})

    def as_json(self) -> dict:
        return {
            "devise": self.devise,
            "total": _total(self.calls),
            # Sans ce drapeau, un total à `null` ne dirait pas POURQUOI il manque.
            "tarification_complete": not self.modeles_sans_tarif,
            "modeles_sans_tarif": self.modeles_sans_tarif,
            "par_typologie": {typologie: self.somme(typologie) for typologie in TYPOLOGIES},
            "appels": [call.as_json() for call in self.calls],
        }

    def somme(self, typologie: str) -> dict:
        calls = self._de(typologie)
        somme = {
            "appels": len(calls),
            "tokens_entree": sum(call.input_tokens for call in calls),
            "tokens_sortie": sum(call.output_tokens for call in calls),
            "tokens_raisonnement": sum(call.reasoning_tokens for call in calls),
            "cout": _total(calls),
            "modeles": sorted({call.model for call in calls}),
        }
        caracteres = sum(call.characters for call in calls)
        if caracteres:
            somme["caracteres"] = caracteres
        return somme

    # -- récapitulatif -------------------------------------------------------

    def texte(self) -> str:
        """Ce que la journée a consommé, poste par poste puis en tout.

        Un poste sans le moindre appel est tu : le journal garde ses zéros pour qui
        recompte, mais trois lignes à zéro dans la console noient les deux qui portent
        quelque chose — et une journée relue du cache n'a que des zéros à dire.
        """
        if not self.calls:
            # Ni total ni postes : une journée entièrement relue du cache, ou un
            # `--dry-run`, n'a rien dépensé, et un « 0.000000 USD » laisserait croire
            # qu'on a mesuré quelque chose.
            return f"{RECAP_PREFIXE} : aucun appel au fournisseur"
        lignes = [f"{RECAP_PREFIXE} :"]
        lignes.extend(
            f"  {LIBELLE_TYPOLOGIE[typologie]} : {self._volume(self._de(typologie))}"
            for typologie in TYPOLOGIES
            if self._de(typologie)
        )
        lignes.append(f"  total : {self._volume(self.calls)}, {self._prix()}")
        return "\n".join(lignes)

    def _de(self, typologie: str) -> list[Call]:
        return [call for call in self.calls if call.typologie == typologie]

    @staticmethod
    def _volume(calls: list[Call]) -> str:
        """Ce qu'un poste a consommé : appels, tokens, et caractères s'il y en a.

        Les caractères ne s'affichent que là où ils existent — la synthèse vocale
        facturée à la longueur du texte. Sa ligne se lirait sinon « 0 token en entrée,
        0 en sortie », soit l'exact contraire de ce qu'elle est : le poste le plus cher
        de la journée.
        """
        caracteres = sum(call.characters for call in calls)
        return (
            f"{len(calls)} appel(s), "
            f"{sum(call.input_tokens for call in calls)} token(s) en entrée, "
            f"{sum(call.output_tokens for call in calls)} en sortie"
            + (f", {caracteres} caractère(s) de synthèse" if caracteres else "")
        )

    def _prix(self) -> str:
        """Le total en toutes lettres, ou la raison pour laquelle il n'y en a pas.

        Un total muet est pire que pas de total : celui qui lit « 0.001234 USD » sans
        savoir qu'un modèle manque à l'appel reporte un chiffre faux. La ligne nomme
        donc les modèles non tarifés et dit par où les déclarer.
        """
        manquants = self.modeles_sans_tarif
        if manquants:
            return (
                f"coût inconnu : {len(manquants)} modèle(s) sans tarif "
                f"({', '.join(manquants)}), à déclarer dans RSSRESUME_PRICES"
            )
        # La synthèse vocale facturée au token ne rend aucun compteur : son coût est
        # déduit du texte, et le total qui la contient est approché.
        approche = "environ " if any(call.estimated for call in self.calls) else ""
        return f"{approche}{_total(self.calls):.6f} {self.devise}"


class Journal:
    """Ce que tout journal tient : les appels au fournisseur et ce qu'ils ont coûté.

    Extrait de `CategoryJournal` le jour où l'éphéméride a eu besoin d'être facturée à
    la journée et non à une catégorie. Deux journaux, la même comptabilité — la
    dupliquer aurait fait deux tables de coûts qui finissent par ne plus s'additionner
    de la même façon.
    """

    def __init__(self):
        self.calls: list[Call] = []
        #: Les journaux que celui-ci a enveloppés — les catégories, sous la journée.
        #: Séparés de `calls` et non versés dedans : chaque journal écrit sa propre
        #: dépense, et un `journee.json` qui reprendrait les appels des catégories les
        #: compterait deux fois pour qui additionne les fichiers d'une journée.
        self.enfants: list[Journal] = []

    def rattacher(self, enfant: Journal) -> None:
        self.enfants.append(enfant)

    def tous_les_appels(self) -> list[Call]:
        """Les appels de ce journal et de tous ceux qu'il a enveloppés."""
        return [
            *self.calls,
            *(call for enfant in self.enfants for call in enfant.tous_les_appels()),
        ]

    def cumul(self) -> Comptes:
        """La somme de la journée : ce journal plus ses descendants.

        Rien sur le disque ne la porte — chaque catégorie a écrit la sienne, personne
        n'additionne — et elle n'a de sens qu'en mémoire, une fois tous les scopes
        refermés.
        """
        return Comptes(self.tous_les_appels())

    def recapitulatif(self) -> str:
        """Le texte du récapitulatif de fin d'exécution, à confier à la console.

        Construit ici et non par l'appelant : c'est ce module qui sait ce qu'il a
        compté, ce qu'il n'a pas pu tarifer, et dans quelle devise.
        """
        return self.cumul().texte()

    def record_chat(self, label: str, model: str, usage: dict | None) -> None:
        """Enregistre une complétion à partir du bloc `usage` de la réponse."""
        usage = usage or {}
        entree = _int(usage.get("prompt_tokens"))
        sortie = _int(usage.get("completion_tokens"))
        raisonnement = _int(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        )
        self.calls.append(
            Call(
                typologie=TYPOLOGIE_PAR_LABEL.get(label, TYPOLOGIE_PAR_DEFAUT),
                label=label,
                model=model,
                input_tokens=entree,
                output_tokens=sortie,
                reasoning_tokens=raisonnement,
                cost=pricing.cost(model, input_tokens=entree, output_tokens=sortie),
            )
        )

    def record_tts(self, model: str, voice: str, text: str) -> None:
        """Enregistre une synthèse vocale : elle ne rend aucun compteur, seul le texte compte."""
        caracteres = len(text or "")
        tokens = pricing.tokens_from_characters(caracteres)
        prix = pricing.tarif(model) or {}
        self.calls.append(
            Call(
                typologie="tts",
                label="tts",
                model=model,
                # Un tarif au caractère n'a pas de tokens à afficher : les estimer
                # laisserait croire à une facturation qui n'a pas lieu.
                input_tokens=0 if "characters" in prix else tokens,
                characters=caracteres,
                cost=pricing.cost(model, input_tokens=tokens, characters=caracteres),
                # Au caractère, le compte est exact ; au token, il est estimé.
                estimated=bool(prix) and "characters" not in prix,
                detail={"voix": voice} if voice else {},
            )
        )

    def _couts(self) -> dict:
        """Le bloc `couts` du fichier : les appels de CE journal, pas ceux de ses enfants.

        Une catégorie facture ce qu'elle a dépensé, et rien d'autre : c'est ce qui rend
        les fichiers d'une journée additionnables entre eux.
        """
        return Comptes(self.calls).as_json()


class DayJournal(Journal):
    """Le journal de la journée : ce qui n'appartient à aucune catégorie.

    Une seule chose y figure aujourd'hui — l'éphéméride d'ouverture, et l'appel qui l'a
    produite. C'est peu, mais c'est ce qui permet à `--send-only` de renvoyer un email
    identique à l'original : sans ce fichier, le renvoi devrait soit repayer l'appel,
    soit ouvrir la lettre sur une autre phrase que celle qui est partie la première fois.

    Il est aussi le journal actif hors de toute catégorie : un appel passé entre deux
    catégories s'y range, au lieu d'être perdu comme il l'était avant.
    """

    def __init__(self, day: dt.date, day_dir: pathlib.Path):
        super().__init__()
        self.day = day
        self.day_dir = day_dir
        self.ephemeride: Ephemeride | None = None

    def set_ephemeride(self, ephemeride: Ephemeride | None) -> None:
        self.ephemeride = ephemeride

    @property
    def path(self) -> pathlib.Path:
        return self.day_dir / DAY_LOG_NAME

    @property
    def worth_writing(self) -> bool:
        """Faux pour une journée qui n'a rien à dire d'elle-même.

        Une éphéméride tirée du calendrier ne vaut pas un fichier : elle se recalcule à
        l'identique à partir de la seule date, et l'écrire ferait un journal qui ne
        transporte rien. Celle du modèle, elle, ne se retrouve pas sans la repayer.
        """
        return bool(self.calls) or (
            self.ephemeride is not None and self.ephemeride.origine != "calendrier"
        )

    def write(self) -> pathlib.Path | None:
        if not self.worth_writing:
            return None
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def as_json(self) -> dict:
        return {
            "date": self.day.isoformat(),
            "genere_le": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            # `jour` est celui de l'envoi, pas celui du journal : c'est ce qui permet
            # au renvoi de savoir si cette éphéméride parle encore du bon jour.
            "ephemeride": (
                {
                    "jour": self.ephemeride.jour.isoformat(),
                    "fete": self.ephemeride.fete,
                    "texte": self.ephemeride.texte,
                    "origine": self.ephemeride.origine,
                }
                if self.ephemeride
                else None
            ),
            "couts": self._couts(),
        }


class CategoryJournal(Journal):
    """Le journal d'une catégorie, du premier article lu au fichier écrit."""

    def __init__(
        self,
        category: str,
        slug: str,
        day: dt.date,
        day_dir: pathlib.Path,
        parametres: dict[str, Any] | None = None,
    ):
        super().__init__()
        self.category = category
        self.slug = slug
        self.day = day
        self.day_dir = day_dir
        self.parametres = parametres or {}
        self.articles: list[Article] = []
        self.notes: dict[str, Note] = {}
        self.new_notes: dict[str, Note] = {}
        self.selected: list[Article] = []
        #: Le seuil réellement appliqué à la journée, repli compris. `None` tant que la
        #: sélection n'a pas eu lieu — une catégorie interrompue avant, notamment.
        self.seuil_applique: int | None = None
        self.digest: CategoryDigest | None = None

    # -- alimentation ------------------------------------------------------

    def set_seuil_applique(self, seuil: int) -> None:
        """Le seuil qui a réellement trié la journée : celui de la catégorie, ou son repli.

        Il ne se déduit pas de `parametres` : c'est le nombre d'articles du jour qui
        décide entre le seuil et son repli, et sans lui un journal de dix articles à
        cinq de moyenne ne dit pas pourquoi ils sont tous retenus.
        """
        self.seuil_applique = seuil

    def set_notes(self, notes: dict[str, Note], new_notes: dict[str, Note]) -> None:
        self.notes = notes
        self.new_notes = new_notes

    def set_digest(self, digest: CategoryDigest) -> None:
        self.digest = digest
        self.articles = digest.articles
        self.selected = digest.selected

    # -- rendu -------------------------------------------------------------

    @property
    def path(self) -> pathlib.Path:
        return self.day_dir / f"{self.slug}{LOG_SUFFIX}"

    @property
    def worth_writing(self) -> bool:
        """Faux pour une catégorie qui s'est terminée sans le moindre article.

        Elle n'a rien lu, rien noté, rien dépensé : le journal ne dirait que des zéros,
        là où le marqueur `.no-article` dit déjà tout. Une catégorie interrompue, elle,
        s'écrit toujours — c'est le cas où le journal sert le plus.
        """
        return self.digest is None or bool(self.articles)

    def write(self) -> pathlib.Path | None:
        if not self.worth_writing:
            return None
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def as_json(self) -> dict:
        return {
            "categorie": self.category,
            "date": self.day.isoformat(),
            "genere_le": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "parametres": self.parametres,
            # Le texte du résumé, seule pièce du digest que le journal ne gardait pas.
            # L'audio le dit à voix haute et l'email l'écrit, mais aucun des deux ne se
            # relit : sans lui, renvoyer l'email d'une journée passée obligeait à repayer
            # le scoring, le résumé et la synthèse vocale pour retrouver un texte déjà écrit.
            "resume": self.digest.summary_text if self.digest else "",
            "resultat": self._resultat(),
            "couts": self._couts(),
            "articles": self._articles(),
        }

    def _resultat(self) -> dict:
        digest = self.digest
        audio = digest.audio_path if digest else None
        marqueur = digest.marker_path if digest else None
        return {
            "statut": self._statut(),
            "articles": len(self.articles),
            "retenus": len(self.selected),
            "seuil_applique": self.seuil_applique,
            "notes_relues_des_tags": len(self.notes) - len(self.new_notes),
            "notes_calculees": len(self.new_notes),
            "audio": audio.name if audio else None,
            "marqueur": marqueur.name if marqueur else None,
        }

    def _statut(self) -> str:
        if self.digest is None:
            # Le scope s'est refermé sur une exception : le journal part quand même,
            # c'est justement le cas où il sert le plus.
            return "interrompu"
        if not self.articles:
            # Jamais écrit sur disque (voir `worth_writing`), mais le statut reste juste
            # pour qui lit le journal en mémoire.
            return "aucun-article"
        if not self.selected:
            return "aucun-article-retenu"
        return "audio" if self.digest.audio_path else "sans-audio"

    def _articles(self) -> list[dict]:
        """Tous les articles lus, les mieux notés en tête, retenus comme écartés.

        L'ordre est celui du score et non celui du digest : le journal sert d'abord à
        juger le seuil, donc à voir ce qui est passé juste à côté.
        """
        rangs = {article.item_id: rang for rang, article in enumerate(self.selected, start=1)}
        classes = sorted(self.articles, key=lambda article: self._note(article).score, reverse=True)
        return [self._article(article, rangs) for article in classes]

    def _article(self, article: Article, rangs: dict[str, int]) -> dict:
        note = self.notes.get(article.item_id)
        return {
            "item_id": article.item_id,
            "titre": article.title,
            "flux": article.feed_title,
            "url": article.url,
            "publie_le": article.published_at.isoformat() if article.published_at else None,
            "score": note.score if note else None,
            "thematique": note.thematique if note else None,
            # Vide pour une note relue des tags : l'angle n'y est pas persisté.
            "angle": note.angle if note else "",
            "origine_note": self._origine(article),
            "retenu": article.item_id in rangs,
            "rang_digest": rangs.get(article.item_id),
        }

    def _origine(self, article: Article) -> str:
        """D'où vient la note : calculée à cette exécution, relue des tags, ou absente."""
        if article.item_id in self.new_notes:
            return "calculee"
        if article.item_id in self.notes:
            return "tags"
        return "aucune"

    def _note(self, article: Article) -> Note:
        return self.notes.get(article.item_id) or Note(score=0)


#: Journal de la catégorie en cours, `None` hors de tout `category_scope`.
_actif: Journal | None = None


def active() -> Journal | None:
    return _actif


@contextlib.contextmanager
def day_scope(day: dt.date, day_dir: pathlib.Path) -> Iterator[DayJournal]:
    """Ouvre le journal de la journée, et l'écrit à la sortie — même sur exception.

    Il enveloppe les `category_scope`, qui prennent la main chacun à leur tour et la
    lui rendent. Un appel passé hors de toute catégorie — l'éphéméride d'ouverture —
    se range donc ici, là où il n'était compté nulle part avant.
    """
    global _actif
    precedent = _actif
    journal = DayJournal(day, day_dir)
    _actif = journal
    try:
        yield journal
    finally:
        _actif = precedent
        journal.write()


def read_ephemeride(day_dir: pathlib.Path) -> Ephemeride | None:
    """L'éphéméride écrite par une journée passée, `None` si elle n'en a pas laissé.

    `None` n'est pas une anomalie : une journée dont l'éphéméride venait du calendrier
    n'a rien écrit, puisqu'elle se recalcule. C'est à l'appelant de redescendre sur ce
    repli — voir `ephemeride.calendrier`.
    """
    path = day_dir / DAY_LOG_NAME
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    bloc = journal.get("ephemeride") or {}
    texte = (bloc.get("texte") or "").strip()
    if not texte:
        return None
    try:
        jour = dt.date.fromisoformat(bloc["jour"])
    except (KeyError, TypeError, ValueError):
        # Journal écrit avant que le jour d'envoi y figure : sans lui, impossible de
        # savoir de quelle date cette éphéméride parle. L'appelant la remplacera.
        return None
    return Ephemeride(
        jour=jour,
        fete=bloc.get("fete") or "",
        texte=texte,
        origine=bloc.get("origine") or "table",
    )


@contextlib.contextmanager
def category_scope(
    category: str,
    slug: str,
    day: dt.date,
    day_dir: pathlib.Path,
    parametres: dict[str, Any] | None = None,
) -> Iterator[CategoryJournal]:
    """Ouvre le journal d'une catégorie, et l'écrit à la sortie — même sur exception.

    Il se rattache au journal qui l'enveloppe en se refermant : sans ce lien, la journée
    ne saurait à la fin que ce qu'elle a payé elle-même, et la somme des catégories
    n'existerait nulle part ailleurs que dans les fichiers déjà écrits. Le rattachement
    a lieu même quand la catégorie a échoué — c'est là qu'elle a dépensé sans rendre.
    """
    global _actif
    precedent = _actif
    journal = CategoryJournal(category, slug, day, day_dir, parametres)
    _actif = journal
    try:
        yield journal
    finally:
        _actif = precedent
        if precedent is not None:
            precedent.rattacher(journal)
        journal.write()


def record_chat(label: str, model: str, usage: dict | None) -> None:
    """Enregistre une complétion dans le journal actif, s'il y en a un."""
    if _actif is not None:
        _actif.record_chat(label, model, usage)


def record_tts(model: str, voice: str, text: str) -> None:
    """Enregistre une synthèse vocale dans le journal actif, s'il y en a un."""
    if _actif is not None:
        _actif.record_tts(model, voice, text)


def _total(calls: list[Call]) -> float | None:
    """Somme des coûts : `0.0` sans aucun appel, `None` dès qu'un appel n'est pas tarifé.

    Pas de somme partielle : un total amputé d'un modèle inconnu se lit exactement
    comme un total complet, et c'est un chiffre que quelqu'un reportera un jour dans
    un tableur. `modeles_sans_tarif` dit lequel manque, `RSSRESUME_PRICES` le comble.
    """
    if not calls:
        return 0.0
    if any(call.cost is None for call in calls):
        return None
    return _round(sum(call.cost for call in calls))


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _round(value: float | None) -> float | None:
    """Arrondi d'affichage. Six décimales : un scoring coûte quelques millièmes de dollar."""
    return None if value is None else round(value, 6)

