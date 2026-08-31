"""Le contrat que remplit un fournisseur de LLM, et la fabrique qui en rend un.

Un `LLMProvider` reçoit ses réglages au constructeur et sait faire cinq choses :
noter des articles, résumer un article, écrire le digest d'une catégorie, rendre
l'éphéméride d'une date, dire un texte. Ce sont ces cinq opérations que le reste du
projet appelle — jamais un endpoint, jamais un payload.

La classe de base fait tout ce qui ne dépend pas du fournisseur : assembler les
prompts, découper le lot de notation, relire les réponses, tenir la comptabilité.
Une sous-classe (`openai.py`, `mistral.py`) ne redéfinit que ce qui diffère
vraiment — la forme d'une requête et celle d'une réponse, soit quatre méthodes
courtes. Un troisième fournisseur, c'est un fichier de plus et un bloc dans
`providers.json`, rien d'autre.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from rssresume import runlog
from rssresume.llm import processing, prompts, providers
from rssresume.llm.providers import (
    ARTICLE,
    DIGEST,
    EPHEMERIDE,
    MONTAGE,
    SCORING,
    TTS,
    Call,
    Settings,
    Voice,
)
from rssresume.tools import console, http

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Échec côté fournisseur : requête rejetée, réponse tronquée ou inexploitable."""


class TruncatedResponse(LLMError):
    """Réponse coupée par le plafond de sortie, avant d'être complète.

    Nommée à part parce qu'elle se rattrape là où les autres échecs ne se rattrapent
    pas : sur la notation, un lot deux fois plus court tient dans le même plafond. Pour
    les autres actions, elle reste ce qu'elle a toujours été — une `LLMError` fatale.
    """


class LLMProvider:
    """Le contrat commun. Instancié via `for_action()`, pas directement."""

    #: Renseignés par les sous-classes.
    CHAT_PATH = "/chat/completions"
    SPEECH_PATH = "/audio/speech"

    def __init__(self, settings: Settings):
        self._settings = settings

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"{type(self).__name__}({self._settings.name})"

    @property
    def name(self) -> str:
        return self._settings.name

    @property
    def label(self) -> str:
        return self._settings.label

    @property
    def voice(self) -> Voice:
        return self._settings.voice

    def model(self, action: str) -> str:
        """Le modèle d'une action, pour le journal et l'affichage."""
        return self._settings.voice.model if action == TTS else self._settings.call(action).model

    # -- ce qu'une sous-classe redéfinit ------------------------------------

    def chat_payload(self, call: Call, system: str, user: str) -> dict:
        """Le corps d'une requête de complétion, dans le dialecte du fournisseur."""
        raise NotImplementedError

    def read_chat(self, response: dict) -> tuple[str, dict | None, bool]:
        """(texte, bloc `usage`, réponse tronquée)."""
        raise NotImplementedError

    def speech_payload(self, voice: Voice, text: str) -> dict:
        """Le corps d'une requête de synthèse vocale."""
        raise NotImplementedError

    def read_speech(self, raw: bytes) -> bytes:
        """Les octets audio, extraits de la réponse."""
        raise NotImplementedError

    # -- les opérations métier ----------------------------------------------

    def score_articles(self, articles: list[dict], profil: str | None = None) -> list[dict]:
        """Note la pertinence de chaque article, sur titre + résumé court uniquement.

        Renvoie un dict {id, score, thematique, angle} par article d'entrée, dans le même
        ordre. Le lot est découpé : au-delà de `SCORING_BATCH_SIZE`, le modèle survole et
        la fin du lot se dégrade.
        """
        logger.info("Scoring : %d article(s) en entrée", len(articles))
        if not articles:
            return []

        taille = prompts.SCORING_BATCH_SIZE
        scored: list[dict] = []
        for depart in range(0, len(articles), taille):
            lot = articles[depart : depart + taille]
            logger.info(
                "Scoring : lot %d, articles %d à %d",
                depart // taille + 1,
                depart + 1,
                depart + len(lot),
            )
            scored.extend(self._score_batch(lot, profil))

        if len(scored) != len(articles):
            raise processing.ProcessingError(
                f"Scoring incomplet : {len(articles)} entrées, {len(scored)} sorties."
            )
        logger.info("Scoring : %d article(s) en sortie", len(scored))
        return scored

    def summarize_article(self, article: dict, profil: str | None = None) -> str:
        """Résumé de 3 à 4 phrases d'un article, sur son texte intégral."""
        return self._chat(
            ARTICLE,
            prompts.article_system(profil),
            prompts.article_user(
                article.get("title") or "",
                article.get("source") or "",
                processing.full_text(article),
            ),
        )

    def write_digest(
        self,
        category: str,
        articles: list[dict],
        language: str = "fr",
        profil: str | None = None,
    ) -> str:
        """Le texte du digest d'une catégorie, celui qui part en synthèse vocale."""
        return self._chat(
            DIGEST,
            prompts.digest_system(profil),
            prompts.digest_user(category, articles, language),
        )

    def write_ephemeride(self, day) -> str:
        """L'événement du domaine survenu à cette date, ou `AUCUN` si le modèle n'en sait rien.

        Un appel par journée, et non par catégorie : il ouvre la lettre entière. La
        réponse n'est pas relue ici — c'est `ephemeride.py` qui décide si elle est
        exploitable, et vers quoi descendre sinon.
        """
        return self._chat(EPHEMERIDE, prompts.ephemeride_system(), prompts.ephemeride_user(day))

    def write_montage(
        self,
        sections: list[dict],
        jour: str,
        muettes: list[str],
        language: str = "fr",
        profil: str | None = None,
        prenom: str = "",
    ) -> str:
        """Le texte de l'audio unique d'une journée, celui qui part en synthèse vocale.

        Un appel par journée et non par catégorie, comme l'éphéméride — et seulement en
        mode `global` : le mode par catégorie ne le paie jamais. L'entrée n'est pas faite
        d'articles mais des résumés déjà écrits : ce chemin ne relit aucun contenu de flux.
        """
        return self._chat(
            MONTAGE,
            prompts.montage_system(profil, prenom),
            prompts.montage_user(sections, jour, muettes, language),
        )

    def speak(self, text: str) -> bytes:
        """Synthèse vocale ; renvoie les octets audio, quel que soit l'emballage reçu."""
        voice = self._settings.voice
        raw = self._post(self.SPEECH_PATH, self.speech_payload(voice, text), TTS)
        try:
            audio = self.read_speech(raw)
        except ValueError as exc:
            raise LLMError(f"{self.label} tts : {exc}") from exc
        # La synthèse ne rend aucun compteur : le texte envoyé est la seule assiette de
        # facturation. Enregistré après l'appel, pour ne rien compter d'une requête rejetée.
        runlog.record_tts(voice.model, voice.voice, text)
        return audio

    def scoring_fingerprint(self, profil: str | None = None) -> str:
        """Empreinte du prompt de notation, modèle compris.

        Sert de clé de cache : tant qu'elle ne change pas, un article déjà noté n'est pas
        renoté. Changer de profil, de barème, de modèle — ou de fournisseur, puisque le
        modèle en dépend — produit une empreinte différente et déclenche la renotation.
        """
        return processing.scoring_fingerprint(profil, self._settings.call(SCORING).model)

    # -- transport -----------------------------------------------------------

    def _chat(self, action: str, system: str, user: str) -> str:
        """Un aller-retour de complétion ; renvoie le texte de la réponse."""
        call = self._settings.call(action)
        payload = self.chat_payload(call, system, user)
        response = json.loads(self._post(self.CHAT_PATH, payload, action).decode("utf-8"))
        text, usage, tronquee = self.read_chat(response)
        # Les compteurs ne reviennent qu'ici : c'est le seul endroit où le coût est connu.
        # Le journal les range sous la catégorie en cours.
        runlog.record_chat(action, call.model, usage)
        if tronquee:
            # Sans ce garde-fou, une réponse coupée ressort en erreur de parsing bien plus
            # loin. Sur un modèle raisonnant, le plafond a pu partir en raisonnement.
            raise TruncatedResponse(
                f"{self.label} {action} : réponse tronquée par le plafond de sortie "
                f"({call.max_tokens}) sur le modèle {call.model}."
            )
        return text

    def _post(self, path: str, payload: dict, label: str) -> bytes:
        """POST JSON, et renvoie le corps brut de la réponse.

        Rejoué sur un échec passager : un 429 ou un 502 du fournisseur ne doit pas coûter
        la journée. Le détail du réessai est dans `tools/http.py`.
        """
        request = urllib.request.Request(
            f"{self._settings.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json",
            },
        )

        def _envoyer() -> bytes:
            with urllib.request.urlopen(request) as response:
                return response.read()

        try:
            return http.retry(_envoyer, f"{self.label} {label}")
        except urllib.error.HTTPError as exc:
            corps = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"{self.label} {label} : {exc.code} {corps}") from exc

    # -- interne -------------------------------------------------------------

    def _score_batch(self, lot: list[dict], profil: str | None) -> list[dict]:
        """Note un lot en un seul appel, en le redécoupant si la réponse est coupée.

        Un lot qui ne tient pas dans le plafond de sortie tuait la journée entière. Il
        n'y a pourtant rien à comprendre : la même consigne sur deux fois moins
        d'articles rend deux fois moins de JSON. On redescend donc jusqu'à
        `SCORING_MIN_BATCH` — en dessous, ce n'est plus la taille qui est en cause, et
        insister ne ferait que repayer le même appel.
        """
        try:
            brut = self._chat(
                SCORING, prompts.scoring_system(profil), prompts.scoring_user(self._lot(lot))
            )
        except TruncatedResponse:
            if len(lot) <= prompts.SCORING_MIN_BATCH:
                raise
            moitie = len(lot) // 2
            console.detail(
                f"scoring : réponse tronquée sur {len(lot)} article(s), "
                f"redécoupage en {moitie} + {len(lot) - moitie}"
            )
            logger.warning(
                "Scoring : lot de %d tronqué, redécoupé en %d + %d",
                len(lot),
                moitie,
                len(lot) - moitie,
            )
            return self._score_batch(lot[:moitie], profil) + self._score_batch(
                lot[moitie:], profil
            )
        return processing.read_scores(brut, lot)

    @staticmethod
    def _lot(lot: list[dict]) -> list[dict]:
        """Le lot tel que le modèle le voit : un numéro, un titre, un résumé court."""
        payload = [
            {
                # Numéro local, jamais l'identifiant FreshRSS : une chaîne du genre
                # `tag:google.com,2005:reader/item/000659ce0338ac4f` revient altérée
                # trop souvent pour qu'on la confie au modèle.
                "id": str(rang),
                "titre": article.get("title") or "",
                # Un résumé absent est fréquent : on l'explicite plutôt qu'envoyer du vide.
                "resume": (article.get("summary") or "").strip() or "(aucun résumé fourni)",
            }
            for rang, article in enumerate(lot, start=1)
        ]
        return payload


# -- fabrique ----------------------------------------------------------------


def adapters() -> dict[str, type[LLMProvider]]:
    """Les sous-classes livrées, indexées par le nom que porte `providers.json`.

    Import local : les sous-classes importent ce module pour en hériter, donc les
    charger au niveau du module ferait un cycle.
    """
    from rssresume.llm import mistral, openai

    return {
        openai.OpenAIProvider.NAME: openai.OpenAIProvider,
        mistral.MistralProvider.NAME: mistral.MistralProvider,
    }


def build(settings: Settings) -> LLMProvider:
    """Le fournisseur décrit par ces réglages. Erreur claire s'il n'a pas d'adaptateur.

    Un fournisseur peut être déclaré dans `providers.json` sans adaptateur — une
    passerelle compatible qu'on n'a pas nommée ainsi. Le dire ici vaut mieux que
    laisser la requête partir dans le mauvais dialecte.
    """
    classes = adapters()
    if settings.name not in classes:
        raise LLMError(
            f"Aucun adaptateur pour le fournisseur '{settings.name}'. "
            f"Connus : {', '.join(sorted(classes))}."
        )
    return classes[settings.name](settings)


def for_action(action: str) -> LLMProvider | None:
    """Le fournisseur d'une action, `None` si sa clé d'API est absente.

    `None` n'est pas une erreur : c'est ce qui fait retomber le résumé sur l'extractif
    local et la synthèse sur `espeak`. Chaque action a son fournisseur, donc sa propre
    clé — une action sans clé n'emprunte jamais celle d'une autre.
    """
    settings = providers.settings(providers.chosen(action))
    return build(settings) if settings.configured else None
