"""Journal d'exécution : un fichier `<catégorie>.log.json` par catégorie et par jour.

Ce que les appels IA coûtent n'est nulle part une fois l'exécution finie. Le journal
le fixe, catégorie par catégorie, à côté de l'audio du jour :

- les articles lus et ce que le scoring en a fait (score, thématique, angle, retenu
  ou non, note calculée ou relue des tags) ;
- le coût des appels IA, détaillé par typologie — la somme des scorings, celle des
  résumés, celle de la synthèse vocale — et le détail appel par appel.

Une catégorie sans article du jour n'écrit aucun journal : elle ne lit rien, ne note
rien et ne dépense rien, et son marqueur `.no-article` dit déjà tout ce qu'il y a à dire.

Le journal actif est un état de module : les appels au fournisseur partent du fond
de `llm.py`, qui n'a aucune raison de savoir quelle catégorie est en cours. Le
pipeline est séquentiel — une catégorie à la fois — et ce module l'est donc aussi.
Hors de tout `category_scope`, tout enregistrement est un no-op : `processing.py`
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
from rssresume.models import Article, CategoryDigest, Note

#: Extension du journal, à côté du `.mp3` ou du `.no-article` de la même catégorie.
LOG_SUFFIX = ".log.json"

#: Les trois postes de dépense demandés, dans l'ordre où ils sont engagés.
TYPOLOGIES = ("scoring", "resume", "tts")

#: Type d'appel (`llm.ChatProfile.label`) rangé sous son poste de dépense. Le résumé
#: par article et le digest de catégorie sont deux façons de résumer : même poste.
TYPOLOGIE_PAR_LABEL = {
    "scoring": "scoring",
    "article summary": "resume",
    "digest": "resume",
    "tts": "tts",
}
TYPOLOGIE_PAR_DEFAUT = "resume"


@dataclasses.dataclass
class Call:
    """Un appel au fournisseur, avec ce qu'il a consommé et ce qu'il a coûté."""

    typologie: str
    #: Type d'appel tel que `llm.py` le nomme : scoring, article summary, digest, tts.
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


class CategoryJournal:
    """Le journal d'une catégorie, du premier article lu au fichier écrit."""

    def __init__(
        self,
        category: str,
        slug: str,
        day: dt.date,
        day_dir: pathlib.Path,
        parametres: dict[str, Any] | None = None,
    ):
        self.category = category
        self.slug = slug
        self.day = day
        self.day_dir = day_dir
        self.parametres = parametres or {}
        self.calls: list[Call] = []
        self.articles: list[Article] = []
        self.notes: dict[str, Note] = {}
        self.new_notes: dict[str, Note] = {}
        self.selected: list[Article] = []
        self.digest: CategoryDigest | None = None

    # -- alimentation ------------------------------------------------------

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

    def _couts(self) -> dict:
        sans_tarif = sorted({call.model for call in self.calls if call.cost is None})
        return {
            "devise": pricing.CURRENCY,
            "total": _total(self.calls),
            # Sans ce drapeau, un total à `null` ne dirait pas POURQUOI il manque.
            "tarification_complete": not sans_tarif,
            "modeles_sans_tarif": sans_tarif,
            "par_typologie": {typologie: self._somme(typologie) for typologie in TYPOLOGIES},
            "appels": [call.as_json() for call in self.calls],
        }

    def _somme(self, typologie: str) -> dict:
        calls = [call for call in self.calls if call.typologie == typologie]
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
_actif: CategoryJournal | None = None


def active() -> CategoryJournal | None:
    return _actif


@contextlib.contextmanager
def category_scope(
    category: str,
    slug: str,
    day: dt.date,
    day_dir: pathlib.Path,
    parametres: dict[str, Any] | None = None,
) -> Iterator[CategoryJournal]:
    """Ouvre le journal d'une catégorie, et l'écrit à la sortie — même sur exception."""
    global _actif
    precedent = _actif
    journal = CategoryJournal(category, slug, day, day_dir, parametres)
    _actif = journal
    try:
        yield journal
    finally:
        _actif = precedent
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

