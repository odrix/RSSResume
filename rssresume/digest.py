"""Orchestration : sélection des catégories, écriture des fichiers, envoi de l'email.

Ce module décide ce que la journée contient ; il ne décide plus de quoi elle a l'air.
La mise en forme de l'email est passée dans `newsletter.py` le jour où l'email a eu un
titre, un sous-titre et un pied de page : elle sert deux chemins — la journée qu'on
vient de produire et celle qu'on renvoie de ses journaux — et elle en avait déjà deux
copies ici, qui commençaient à diverger.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from rssresume import runlog
from rssresume.certfr import CertfrService
from rssresume.config import AppConfig
from rssresume.ephemeride import EphemerideService
from rssresume.external.freshrss import score_from_tags, scoring_digest_from_tags, theme_from_tags
from rssresume.llm import providers
from rssresume.models import (
    WATCHLIST_MAX,
    WATCHLIST_MIN,
    Article,
    CategoryDigest,
    Ephemeride,
    Note,
    Selection,
    SelectionRule,
)
from rssresume.newsletter import Lettre
from rssresume.protocols import (
    AudioGeneratorProtocol,
    CertfrServiceProtocol,
    EmailSenderProtocol,
    EphemerideServiceProtocol,
    FreshRSSClientProtocol,
    ScorerProtocol,
    SummaryGeneratorProtocol,
)
from rssresume.tools import console
from rssresume.tools.text import no_article_message, no_selection_message, slugify

NO_ARTICLE_SUFFIX = ".no-article"

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
        scorer: ScorerProtocol | None = None,
        ephemeride_service: EphemerideServiceProtocol | None = None,
        certfr_service: CertfrServiceProtocol | None = None,
    ):
        self._config = config
        self._freshrss_client = freshrss_client
        self._summary_generator = summary_generator
        self._audio_generator = audio_generator
        self._email_sender = email_sender
        #: Sans service injecté, celui qui n'appelle personne : table embarquée et
        #: calendrier. L'email a toujours son introduction, même monté à la main.
        self._ephemeride_service = ephemeride_service or EphemerideService()
        #: Le tri déterministe des avis CERT-FR, avec une stack vide à défaut — c'est
        #: `cli.build_service` qui lui passe celle du document de profil. Construit
        #: toujours, sollicité seulement par les catégories que
        #: `RSSRESUME_CERTFR_CATEGORIES` route.
        self._certfr_service = certfr_service or CertfrService()
        #: `None` quand aucune clé d'API ne le permet : tous les articles entrent alors
        #: dans le digest, sans note et sans seuil.
        self._scorer = scorer

    def run(
        self,
        day: dt.date,
        send_email: bool = True,
        write_tags: bool = True,
        mark_read: bool = True,
    ) -> list[CategoryDigest]:
        day_dir = self._day_dir(day)
        console.log(f"RSSResume : digest du {day.isoformat()} vers {day_dir}")

        # Le journal de la journée enveloppe ceux des catégories : l'appel de
        # l'éphéméride est le seul qui ne se rattache à aucune d'elles, et sans ce
        # scope il ne serait compté nulle part.
        with runlog.day_scope(day, day_dir) as journal:
            # Le jour de l'ENVOI, pas `day` : le passage de 7 h raconte la veille
            # (`RSSRESUME_SCHEDULE_DAYS_BACK`), et l'introduction doit s'ouvrir sur la
            # date à laquelle la lettre arrive, avec la fête de ce jour-là.
            ephemeride = self._ephemeride_service.of(self._aujourdhui())
            journal.set_ephemeride(ephemeride)

            categories = self._select_categories()
            console.log(f"{len(categories)} catégorie(s) à traiter : {', '.join(categories) or '(aucune)'}")

            if not write_tags:
                console.log("Tags FreshRSS (scores, digest) : ignorés (--no-tags)")

            # Les tags sont écrits catégorie par catégorie : un échec en cours de route
            # ne fait pas perdre les scores déjà calculés, qui seraient repayés au passage suivant.
            digests = [
                self._build_digest(category, day, day_dir, write_tags) for category in categories
            ]

        if not send_email:
            console.log("Email : ignoré (--no-email)")
        elif not self._email_sender.is_configured():
            console.log("Email : ignoré (configuration SMTP incomplète)")
        else:
            self._send_email(day, digests, ephemeride)

        if mark_read:
            # Après livraison seulement : un échec d'envoi ne doit pas perdre les articles.
            self._mark_read(digests)
        else:
            console.log("Marquage comme lu : ignoré (--no-mark-read)")

        # Le scope est refermé et `runlog.active()` vaut de nouveau `None` : c'est la
        # variable liée par le `with` qui porte encore la journée, catégories rattachées
        # comprises. Rien d'autre ne totalise ce que la matinée a coûté.
        console.log(journal.recapitulatif())
        console.log(self._report(digests))
        return digests

    @staticmethod
    def _report(digests: list[CategoryDigest]) -> str:
        audios = sum(1 for digest in digests if digest.audio_path)
        articles = sum(len(digest.articles) for digest in digests)
        retenus = sum(len(digest.selected) for digest in digests)
        vides = sum(1 for digest in digests if not digest.articles)
        # Compté sur la sélection et non par soustraction des audios : une catégorie
        # déterministe n'a pas d'audio sans être pour autant restée les mains vides.
        sans_selection = sum(1 for digest in digests if digest.articles and not digest.selected)
        return (
            f"Terminé : {articles} article(s) lu(s), {retenus} retenu(s), "
            f"{audios} fichier(s) audio, {vides} catégorie(s) sans article"
            + (f", {sans_selection} sans article retenu" if sans_selection else "")
        )

    def _aujourdhui(self) -> dt.date:
        """La date du jour dans le fuseau configuré, c'est-à-dire celle de l'envoi.

        Dans le fuseau et non celui de la machine : l'horloge d'un conteneur est en UTC,
        et à 1 h du matin à Paris elle est encore la veille.
        """
        return dt.datetime.now(self._config.timezone).date()

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
        """Construit la catégorie sous son journal : scores, coûts et suivi sont écrits ensuite.

        Le journal est ouvert ici et non dans `run` : il est indexé par catégorie, et
        c'est ce qui permet aux appels au fournisseur — partis du fond d'un `LLMProvider` — de
        se ranger sous la bonne, sans que rien n'ait à leur transmettre la catégorie.
        """
        slug = slugify(category)
        regle = self._config.selection_rule(category)
        # Le routage est décidé avant d'ouvrir le journal, parce que les deux chemins n'y
        # écrivent pas les mêmes réglages : un seuil et une empreinte de prompt ne veulent
        # rien dire pour une catégorie qui n'a appelé aucun modèle.
        deterministe = self._config.est_deterministe(category)
        parametres = self._parametres_certfr() if deterministe else self._parametres(regle)
        with runlog.category_scope(category, slug, day, day_dir, parametres) as journal:
            if deterministe:
                digest = self._build_certfr(category, day, day_dir, slug)
            else:
                digest = self._build_category(
                    category, day, day_dir, slug, write_tags, journal, regle
                )
            journal.set_digest(digest)
            return digest

    def _scoring_fingerprint(self) -> str | None:
        """L'empreinte du noteur actif, `None` quand il n'y en a pas."""
        return self._scorer.scoring_fingerprint(self._config.profil) if self._scorer else None

    def _parametres(self, regle: SelectionRule) -> dict:
        """Les réglages qui expliquent le contenu du journal, relus sans la config.

        Le seuil est celui de cette catégorie, repli compris : deux catégories du même
        jour n'ont plus forcément le même, et le journal est l'endroit où on le vérifie.
        Le seuil réellement appliqué, lui, est un résultat de la journée : il est dans
        `resultat`, pas ici.
        """
        return {
            "seuil": regle.seuil,
            "seuil_repli": regle.seuil_repli,
            "minimum_retenus": regle.minimum,
            "plafond": regle.plafond,
            "langue": self._config.summary_language,
            # Qui fait quoi : fournisseur et modèle de chaque action, tels qu'ils ont été
            # lus au lancement. Une action dont `actif` est faux est retombée sur le
            # local — extractif pour le résumé, espeak pour la voix.
            "fournisseurs": providers.describe(),
            # L'empreinte du prompt de scoring : deux journaux dont elle diffère n'ont
            # pas noté leurs articles contre le même profil, et ne se comparent pas.
            "empreinte_scoring": self._scoring_fingerprint(),
        }

    def _parametres_certfr(self) -> dict:
        """Les réglages d'une catégorie déterministe : ni seuil, ni modèle, ni prompt.

        Un bloc à part, et non `_parametres` amputé de trois clés. `seuil`,
        `seuil_repli` et `empreinte_scoring` n'ont aucun sens sans scoring : les écrire
        à zéro ferait lire ce journal comme celui d'une catégorie qui n'a rien retenu,
        et les laisser à leur valeur de configuration ferait croire à un tri qui n'a
        pas eu lieu. Ce qui explique le contenu, ici, c'est la liste des composants —
        d'où son empreinte, qui dit si deux journées ont été appariées contre la même.
        """
        stack = self._certfr_service.stack
        return {
            "traitement": runlog.TRAITEMENT_DETERMINISTE,
            "langue": self._config.summary_language,
            "composants": len(stack),
            "empreinte_stack": stack.empreinte,
        }

    def _build_certfr(
        self, category: str, day: dt.date, day_dir: pathlib.Path, slug: str
    ) -> CategoryDigest:
        """La catégorie routée hors du pipeline LLM : ni scoring, ni résumé, ni voix.

        Trois choix, et chacun retombe ailleurs sans une ligne de plus :

        - `articles` porte **tous** les avis, appariés ou non. `_mark_read` aplatit les
          `articles` de tous les digests : les avis qui ne nous touchent pas sont donc
          marqués lus sans avoir été résumés, ce qui était exactement la demande ;
        - `selected` ne porte que les avis qui touchent la stack. `CategoryDigest.links`
          en dérive, et ils remontent dans la liste « À lire » de l'email ;
        - `audio_path` reste `None` : une phrase ne se raconte pas. `newsletter.py` sait
          déjà présenter une section sans audio — pas de badge de durée, pas de pièce
          jointe, et `Section.racontee` suit `selected`, pas le fichier.

        Aucun tag n'est écrit non plus : il n'y a ni note à mettre en cache, ni prompt
        dont il faudrait retenir la version.
        """
        articles = self._freshrss_client.fetch_daily_articles(category, day)
        console.category(category, f"{len(articles)} avis (traitement déterministe)")

        if not articles:
            marker_path = self._write_marker(day_dir, slug)
            console.detail(f"aucun avis : {marker_path.name} (ni IA ni synthèse vocale)")
            return CategoryDigest(
                category=category,
                articles=articles,
                summary_text=no_article_message(category),
                marker_path=marker_path,
            )

        revue = self._certfr_service.lire(articles)
        console.detail(revue.phrase)
        return CategoryDigest(
            category=category,
            articles=articles,
            summary_text=revue.phrase,
            selected=revue.touches,
        )

    def _build_category(
        self,
        category: str,
        day: dt.date,
        day_dir: pathlib.Path,
        slug: str,
        write_tags: bool,
        journal: runlog.CategoryJournal,
        regle: SelectionRule,
    ) -> CategoryDigest:
        articles = self._freshrss_client.fetch_daily_articles(category, day)
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

        notes, new_notes, stale = self._score(articles)
        # Le journal veut toutes les notes, pas seulement celles calculées : c'est la
        # seule vue où un score relu des tags et un score frais se lisent côte à côte.
        journal.set_notes(notes, new_notes)
        selection = self._select(articles, notes, regle)
        journal.set_seuil_applique(selection.seuil)
        selected = self._grouped_by_theme(selection.retenus, notes)

        if not selected:
            # Rien au-dessus du seuil : même marqueur, mais qui liste les scores obtenus.
            # Ni résumé ni synthèse vocale — l'audio n'aurait rien à dire.
            marker_path = self._write_marker(
                day_dir, slug, self._score_listing(articles, notes, selection.seuil)
            )
            console.detail(
                f"aucun article retenu : {marker_path.name} (ni IA ni synthèse vocale)"
            )
            if write_tags:
                # Les notes restent à écrire : sans elles, tout serait renoté au passage suivant.
                self._write_tags(articles, selected, new_notes, stale)
            return CategoryDigest(
                category=category,
                articles=articles,
                summary_text=no_selection_message(category, selection.seuil),
                new_notes=new_notes,
                stale_item_ids=stale,
                marker_path=marker_path,
                # C'est ici que la liste de veille sert le plus : la catégorie n'a rien
                # à raconter, mais elle a lu des articles, et certains valent un lien.
                watchlist=self._watchlist(articles, selected, notes),
            )

        summary_text = self._summary_generator.summarize(category, selected, notes)
        audio_path = self._audio_generator.synthesize(
            summary_text,
            day_dir / f"{slug}{self._audio_generator.extension}",
        )
        console.detail(f"audio écrit : {audio_path.name} ({audio_path.stat().st_size} octets)")

        if write_tags:
            self._write_tags(articles, selected, new_notes, stale)

        return CategoryDigest(
            category=category,
            articles=articles,
            summary_text=summary_text,
            selected=selected,
            new_notes=new_notes,
            stale_item_ids=stale,
            audio_path=audio_path,
            watchlist=self._watchlist(articles, selected, notes),
        )

    @classmethod
    def _watchlist(
        cls, articles: list[Article], selected: list[Article], notes: dict[str, Note]
    ) -> list[Article]:
        """Les articles lus, notés dans la fourchette de veille, et non retenus.

        Ils sont déjà payés : lus, notés, écartés. Les taire revenait à jeter la moitié
        de ce que la journée coûte, alors qu'un titre et un lien suffisent à les rendre
        utiles — c'est exactement la zone où l'on veut savoir sans vouloir écouter.

        Dérivés du score et non d'un second passage du modèle : la fourchette est une
        règle d'affichage, pas un jugement de plus.
        """
        retenus = {article.item_id for article in selected}
        candidats = [
            article
            for article in articles
            if article.item_id not in retenus
            and WATCHLIST_MIN <= cls._score_of(article, notes) <= WATCHLIST_MAX
        ]
        return sorted(candidats, key=lambda article: cls._score_of(article, notes), reverse=True)

    @staticmethod
    def _write_marker(day_dir: pathlib.Path, slug: str, content: str = "") -> pathlib.Path:
        """Écrit le marqueur `.no-article` d'une catégorie sans audio."""
        marker_path = day_dir / f"{slug}{NO_ARTICLE_SUFFIX}"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(content, encoding="utf-8")
        return marker_path

    def _score_listing(self, articles: list[Article], notes: dict[str, Note], seuil: int) -> str:
        """Les notes obtenues, les meilleures d'abord : de quoi juger le seuil sans FreshRSS.

        La thématique y figure aussi : elle est calculée de toute façon, et c'est elle
        qui explique l'ordre de lecture du digest quand il y a une sélection.
        """
        lines = [f"Aucun article retenu sur {len(articles)} (seuil {seuil}).", ""]
        classes = sorted(articles, key=lambda a: self._score_of(a, notes), reverse=True)
        lines.extend(
            f"{self._score_of(a, notes):>2}/10 {self._note_of(a, notes).thematique:<13} - {a.title}"
            for a in classes
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _note_of(article: Article, notes: dict[str, Note]) -> Note:
        """Note de l'article, note neutre si le scoring est désactivé."""
        return notes.get(article.item_id) or Note(score=0)

    @classmethod
    def _score_of(cls, article: Article, notes: dict[str, Note]) -> int:
        return cls._note_of(article, notes).score

    def _score(
        self, articles: list[Article]
    ) -> tuple[dict[str, Note], dict[str, Note], list[str]]:
        """Note les articles, en réutilisant les notes déjà posées comme tags.

        Renvoie (toutes les notes, celles calculées maintenant, les articles à renettoyer).
        Sans API configurée, aucune note : tous les articles entrent dans le digest.
        """
        if self._scorer is None:
            return {}, {}, []

        digest = self._scoring_fingerprint()
        a_noter: list[Article] = []
        stale: list[str] = []
        notes: dict[str, Note] = {}

        for article in articles:
            porte = scoring_digest_from_tags(article.tags)
            score = score_from_tags(article.tags)
            thematique = theme_from_tags(article.tags)
            # La thématique est exigée autant que le score : une note partielle n'est pas
            # un cache utilisable, elle rangerait l'article dans le mauvais groupe.
            if porte == digest and score is not None and thematique is not None:
                # L'angle, lui, n'est pas dans les tags : cet article ira au résumé sans
                # sa phrase de contexte, ce dont le prompt tient compte.
                notes[article.item_id] = Note(score=score, thematique=thematique)
                continue
            a_noter.append(article)
            if porte is not None:
                # Noté par une version antérieure du prompt : ses tags sont à retirer.
                stale.append(article.item_id)

        console.detail(
            f"scoring : {len(notes)} note(s) relue(s) des tags, {len(a_noter)} à calculer"
            + (f", dont {len(stale)} à renoter (prompt modifié)" if stale else "")
        )
        if not a_noter:
            return notes, {}, stale

        calculees = self._scorer.score_articles(
            [self._to_payload(article) for article in a_noter],
            profil=self._config.profil,
        )
        # Un article que le modèle a sauté ressort avec `notee` à faux et un score de
        # remplissage. Il est écarté ici, et de la journée : entrer avec un zéro le
        # ferait taguer `score-00` sous l'empreinte courante, donc relire de ce cache
        # à chaque passage suivant — un accident de lot deviendrait définitif. Sans
        # tag, un rejeu de la journée (`--include-read`) le note de nouveau, et le
        # journal de la catégorie le montre sans note.
        perdues = [note for note in calculees if not note.get("notee", True)]
        if perdues:
            console.detail(
                f"scoring : {len(perdues)} article(s) laissé(s) sans note par le modèle, "
                f"écartés du digest du jour, aucun tag posé"
            )
        new_notes = {
            note["id"]: Note(
                score=note["score"], thematique=note["thematique"], angle=note["angle"]
            )
            for note in calculees
            if note.get("notee", True)
        }
        return {**notes, **new_notes}, new_notes, stale

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

    def _select(
        self, articles: list[Article], notes: dict[str, Note], regle: SelectionRule
    ) -> Selection[Article]:
        """Ce que la règle de la catégorie retient de la journée.

        Sans noteur — aucune API de scoring configurée — il n'y a ni seuil ni plafond à
        appliquer : tout entre, et le seuil rapporté est zéro. La condition porte sur le
        noteur et non sur les notes : une journée dont le scoring a tout perdu doit rendre
        un digest vide, surtout pas la journée entière racontée sans avoir été triée.
        """
        if self._scorer is None:
            return Selection(retenus=articles, seuil=0, regle=regle)

        selection = regle.appliquer(articles, lambda a: self._score_of(a, notes))
        repli = (
            f", seuil abaissé de {regle.seuil} faute de {regle.minimum} article(s) retenu(s)"
            if selection.repliee
            else ""
        )
        console.detail(
            f"sélection : {len(selection.retenus)} article(s) retenu(s) sur {len(articles)} "
            f"(seuil {selection.seuil}){repli}"
        )
        return selection

    @classmethod
    def _grouped_by_theme(cls, articles: list[Article], notes: dict[str, Note]) -> list[Article]:
        """Articles regroupés par thématique, le groupe du meilleur article en tête.

        Le tri par score seul faisait sauter du réglementaire au cyber, puis au marché,
        puis de nouveau au réglementaire : à l'écoute, aucune transition n'est possible.
        Regrouper ne coûte aucun appel — la thématique est déjà notée — et l'urgence
        reste respectée : un groupe est classé sur son meilleur article, et l'ordre à
        l'intérieur du groupe reste le score décroissant.
        """
        groupes: dict[str, list[Article]] = {}
        for article in articles:  # déjà triés par score décroissant
            groupes.setdefault(cls._note_of(article, notes).thematique, []).append(article)
        # Tri stable : à meilleur score égal, le groupe apparu le premier reste devant.
        ordre = sorted(groupes, key=lambda theme: -cls._score_of(groupes[theme][0], notes))
        return [article for theme in ordre for article in groupes[theme]]

    def _write_tags(
        self,
        articles: list[Article],
        selected: list[Article],
        new_notes: dict[str, Note],
        stale: list[str],
    ) -> None:
        """Écrit les tags d'une catégorie, dès que son résumé est produit.

        Le marquage comme lu, lui, attend la livraison : ces tags sont des données de
        cache et de navigation, pas un accusé de livraison.
        """
        a_nettoyer = [article for article in articles if article.item_id in set(stale)]
        if a_nettoyer:
            self._freshrss_client.clear_scoring_tags(a_nettoyer)
        if new_notes:
            self._freshrss_client.tag_notes(new_notes, self._scoring_fingerprint())
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

    def _send_email(
        self, day: dt.date, digests: list[CategoryDigest], ephemeride: Ephemeride | None = None
    ) -> None:
        """Compose la lettre et la confie à l'expéditeur, sous ses deux formes.

        L'audio ne porte aucun lien — une URL lue à voix haute est inutilisable, et une
        URL dans le contexte du modèle est une URL qu'il peut inventer. L'email est donc
        le seul endroit où retrouver l'article derrière un sujet entendu, et c'est
        `newsletter.Lettre` qui décide comment il les présente.
        """
        lettre = Lettre.compose(day, digests, ephemeride)
        self._email_sender.send(
            subject=lettre.subject,
            body=lettre.text,
            attachments=lettre.attachments,
            html=lettre.html,
        )
