"""Orchestration : sélection des catégories, écriture des fichiers, envoi de l'email."""

from __future__ import annotations

import datetime as dt
import pathlib

from rssresume import console, processing
from rssresume.audio import audio_extension
from rssresume.config import AppConfig
from rssresume.freshrss import score_from_tags, scoring_digest_from_tags
from rssresume.models import Article, CategoryDigest
from rssresume.protocols import (
    AudioGeneratorProtocol,
    EmailSenderProtocol,
    FreshRSSClientProtocol,
    SummaryGeneratorProtocol,
)
from rssresume.text import no_article_message, no_selection_message, slugify

NO_ARTICLE_SUFFIX = ".no-article"
BODY_SEPARATOR = "\n\n"
#: Le scoring ne juge que sur un extrait : c'est le résumé, pas le scoring, qui lit tout.
SCORING_EXCERPT_LENGTH = 400


class DigestService:
    def __init__(
        self,
        config: AppConfig,
        freshrss_client: FreshRSSClientProtocol,
        summary_generator: SummaryGeneratorProtocol,
        audio_generator: AudioGeneratorProtocol,
        email_sender: EmailSenderProtocol,
    ):
        self._config = config
        self._freshrss_client = freshrss_client
        self._summary_generator = summary_generator
        self._audio_generator = audio_generator
        self._email_sender = email_sender

    def run(
        self,
        day: dt.date,
        send_email: bool = True,
        write_tags: bool = True,
        mark_read: bool = True,
    ) -> list[CategoryDigest]:
        day_dir = self._day_dir(day)
        console.log(f"RSSResume : digest du {day.isoformat()} vers {day_dir}")

        categories = self._select_categories()
        console.log(f"{len(categories)} catégorie(s) à traiter : {', '.join(categories) or '(aucune)'}")

        if not write_tags:
            console.log("Tags FreshRSS (scores, digest) : ignorés (--no-tags)")

        # Les tags sont écrits catégorie par catégorie : un échec en cours de route
        # ne fait pas perdre les scores déjà calculés, qui seraient repayés au passage suivant.
        digests = [self._build_digest(category, day, day_dir, write_tags) for category in categories]

        if not send_email:
            console.log("Email : ignoré (--no-email)")
        elif not self._email_sender.is_configured():
            console.log("Email : ignoré (configuration SMTP incomplète)")
        else:
            self._send_email(day, digests)

        if mark_read:
            # Après livraison seulement : un échec d'envoi ne doit pas perdre les articles.
            self._mark_read(digests)
        else:
            console.log("Marquage comme lu : ignoré (--no-mark-read)")

        console.log(self._report(digests))
        return digests

    @staticmethod
    def _report(digests: list[CategoryDigest]) -> str:
        audios = sum(1 for digest in digests if digest.audio_path)
        articles = sum(len(digest.articles) for digest in digests)
        retenus = sum(len(digest.selected) for digest in digests)
        vides = sum(1 for digest in digests if not digest.articles)
        sans_selection = len(digests) - audios - vides
        return (
            f"Terminé : {articles} article(s) lu(s), {retenus} retenu(s), "
            f"{audios} fichier(s) audio, {vides} catégorie(s) sans article"
            + (f", {sans_selection} sans article retenu" if sans_selection else "")
        )

    def _day_dir(self, day: dt.date) -> pathlib.Path:
        """Un sous-répertoire par journée, au format yyyy-MM-dd."""
        return self._config.output_dir / day.isoformat()

    def _select_categories(self) -> list[str]:
        categories = self._config.categories or self._freshrss_client.list_categories()
        excluded = {name.casefold() for name in self._config.excluded_categories}
        return [category for category in categories if category and category.casefold() not in excluded]

    def _build_digest(
        self,
        category: str,
        day: dt.date,
        day_dir: pathlib.Path,
        write_tags: bool = True,
    ) -> CategoryDigest:
        articles = self._freshrss_client.fetch_daily_articles(category, day)
        slug = slugify(category)
        console.category(category, f"{len(articles)} article(s)")

        if not articles:
            # Aucun article : marqueur vide, ni résumé IA ni synthèse vocale.
            marker_path = self._write_marker(day_dir, slug)
            console.detail(f"aucun article : {marker_path.name} (ni IA ni synthèse vocale)")
            return CategoryDigest(
                category=category,
                articles=articles,
                summary_text=no_article_message(category),
                marker_path=marker_path,
            )

        scores, new_scores, stale = self._score(articles)
        selected = self._select(articles, scores)

        if not selected:
            # Rien au-dessus du seuil : même marqueur, mais qui liste les scores obtenus.
            # Ni résumé ni synthèse vocale — l'audio n'aurait rien à dire.
            marker_path = self._write_marker(day_dir, slug, self._score_listing(articles, scores))
            console.detail(
                f"aucun article retenu : {marker_path.name} (ni IA ni synthèse vocale)"
            )
            if write_tags:
                # Les scores restent à écrire : sans eux, tout serait renoté au passage suivant.
                self._write_tags(articles, selected, new_scores, stale)
            return CategoryDigest(
                category=category,
                articles=articles,
                summary_text=no_selection_message(category, self._config.score_threshold),
                new_scores=new_scores,
                stale_item_ids=stale,
                marker_path=marker_path,
            )

        summary_text = self._summary_generator.summarize(category, selected)
        audio_path = self._audio_generator.synthesize(
            summary_text,
            day_dir / f"{slug}{audio_extension(self._config)}",
        )
        console.detail(f"audio écrit : {audio_path.name} ({audio_path.stat().st_size} octets)")

        if write_tags:
            self._write_tags(articles, selected, new_scores, stale)

        return CategoryDigest(
            category=category,
            articles=articles,
            summary_text=summary_text,
            selected=selected,
            new_scores=new_scores,
            stale_item_ids=stale,
            audio_path=audio_path,
        )

    @staticmethod
    def _write_marker(day_dir: pathlib.Path, slug: str, content: str = "") -> pathlib.Path:
        """Écrit le marqueur `.no-article` d'une catégorie sans audio."""
        marker_path = day_dir / f"{slug}{NO_ARTICLE_SUFFIX}"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(content, encoding="utf-8")
        return marker_path

    def _score_listing(self, articles: list[Article], scores: dict[str, int]) -> str:
        """Les scores obtenus, les meilleurs d'abord : de quoi juger le seuil sans FreshRSS."""
        lines = [
            f"Aucun article retenu sur {len(articles)} "
            f"(seuil {self._config.score_threshold}).",
            "",
        ]
        classes = sorted(articles, key=lambda a: scores.get(a.item_id, 0), reverse=True)
        lines.extend(f"{scores.get(a.item_id, 0):>2}/10 - {a.title}" for a in classes)
        return "\n".join(lines) + "\n"

    def _score(self, articles: list[Article]) -> tuple[dict[str, int], dict[str, int], list[str]]:
        """Note les articles, en réutilisant les scores déjà posés comme tags.

        Renvoie (tous les scores, ceux calculés maintenant, les articles à renettoyer).
        Sans API configurée, aucun score : tous les articles entrent dans le digest.
        """
        if not self._config.uses_llm:
            return {}, {}, []

        digest = processing.scoring_prompt_digest()
        a_noter: list[Article] = []
        stale: list[str] = []
        scores: dict[str, int] = {}

        for article in articles:
            porte = scoring_digest_from_tags(article.tags)
            score = score_from_tags(article.tags)
            if porte == digest and score is not None:
                scores[article.item_id] = score
                continue
            a_noter.append(article)
            if porte is not None:
                # Noté par une version antérieure du prompt : ses tags sont à retirer.
                stale.append(article.item_id)

        console.detail(
            f"scoring : {len(scores)} score(s) relu(s) des tags, {len(a_noter)} à calculer"
            + (f", dont {len(stale)} à renoter (prompt modifié)" if stale else "")
        )
        if not a_noter:
            return scores, {}, stale

        notes = processing.score_articles(
            [self._to_payload(article) for article in a_noter],
            credentials=(self._config.llm_base_url, self._config.llm_api_key),
        )
        new_scores = {note["id"]: note["score"] for note in notes}
        return {**scores, **new_scores}, new_scores, stale

    @staticmethod
    def _to_payload(article: Article) -> dict:
        """Article converti pour le scoring : titre et extrait court, jamais le texte intégral."""
        return {
            "id": article.item_id,
            "title": article.title,
            "summary": article.content_text[:SCORING_EXCERPT_LENGTH],
            "source": article.feed_title,
            "url": article.url,
        }

    def _select(self, articles: list[Article], scores: dict[str, int]) -> list[Article]:
        """Articles au-dessus du seuil, les mieux notés d'abord, plafonnés."""
        if not scores:
            return articles

        retenus = sorted(
            (a for a in articles if scores.get(a.item_id, 0) >= self._config.score_threshold),
            key=lambda a: scores.get(a.item_id, 0),
            reverse=True,
        )[: self._config.max_digest_items]
        console.detail(
            f"sélection : {len(retenus)} article(s) retenu(s) sur {len(articles)} "
            f"(seuil {self._config.score_threshold})"
        )
        return retenus

    def _write_tags(
        self,
        articles: list[Article],
        selected: list[Article],
        new_scores: dict[str, int],
        stale: list[str],
    ) -> None:
        """Écrit les tags d'une catégorie, dès que son résumé est produit.

        Le marquage comme lu, lui, attend la livraison : ces tags sont des données de
        cache et de navigation, pas un accusé de livraison.
        """
        a_nettoyer = [article for article in articles if article.item_id in set(stale)]
        if a_nettoyer:
            self._freshrss_client.clear_scoring_tags(a_nettoyer)
        if new_scores:
            self._freshrss_client.tag_scores(new_scores, processing.scoring_prompt_digest())
        self._tag_digested(selected)

    def _mark_read(self, digests: list[CategoryDigest]) -> None:
        articles = [article for digest in digests for article in digest.articles]
        if articles:
            self._freshrss_client.mark_as_read(articles)

    def _tag_digested(self, selected: list[Article]) -> None:
        """Tag les articles qui ont alimenté le résumé de cette catégorie."""
        item_ids = [article.item_id for article in selected if article.item_id]
        if item_ids:
            self._freshrss_client.mark_digested(item_ids)

    def _send_email(self, day: dt.date, digests: list[CategoryDigest]) -> None:
        body = BODY_SEPARATOR.join(digest.summary_text for digest in digests)
        self._email_sender.send(
            subject=f"Résumé RSS du {day.isoformat()}",
            body=body or f"Aucun article trouvé pour le {day.isoformat()}.",
            attachments=[digest.audio_path for digest in digests if digest.audio_path],
        )
