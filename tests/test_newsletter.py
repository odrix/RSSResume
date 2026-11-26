"""La lettre : son titre, son sous-titre, son introduction, ses sections, son pied.

Ce que ces tests protègent : les deux rendus doivent dire la même chose. Le HTML porte
la mise en page, le texte reste la seule version qu'un client en texte seul affichera,
et un titre d'article venu d'un flux ne doit jamais s'échapper dans le balisage.
"""

import dataclasses
import datetime as dt
import pathlib
import re
import tempfile
import unittest
import wave

from rssresume.desabonnement import OBJET_DESABONNEMENT, Desabonnement, Signataire
from rssresume.ephemeride import fetes
from rssresume.models import Article, CategoryDigest, Ephemeride, Montage
from rssresume.newsletter import (
    NOM_SERVICE,
    QUESTION_AVIS,
    Abonnement,
    Lettre,
    Section,
    date_longue,
    duree,
)
from rssresume.retours import OBJET_RETOUR, LienRetour
from tests.support import FakeEmailSender, make_config

#: La journée que la lettre raconte, et celle où elle part : le passage de 7 h résume
#: la veille, donc les deux diffèrent tous les matins. Les tests le reproduisent.
JOUR = dt.date(2026, 8, 27)  # un jeudi, la journée racontée
ENVOI = dt.date(2026, 8, 28)  # un vendredi, le jour où la lettre arrive
COMPOSEE_LE = dt.datetime(2026, 8, 28, 7, 30)


def ephem(texte="1991, le Web est présenté publiquement.", jour=ENVOI, origine="table"):
    """Une éphéméride du jour de l'envoi, fête comprise."""
    return Ephemeride(jour=jour, fete=fetes.du_jour(jour), texte=texte, origine=origine)


def article(titre, url, flux="Flux A"):
    return Article(
        item_id=titre,
        category="Tech",
        title=titre,
        url=url,
        published_at=dt.datetime(2026, 8, 30, 8, 0),
        feed_title=flux,
        content_text="",
    )


def digest(categorie="Cyber", resume="Le résumé.", retenus=(), veille=(), audio=None):
    return CategoryDigest(
        category=categorie,
        articles=[],
        summary_text=resume,
        selected=[article(t, u) for t, u in retenus],
        watchlist=[article(t, u) for t, u in veille],
        audio_path=audio,
    )


def wav(dossier, secondes, nom="voix.wav"):
    """Un vrai fichier audio, pour que la durée soit mesurée et non simulée."""
    chemin = pathlib.Path(dossier) / nom
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(16000)
        fichier.writeframes(bytes(2 * 16000 * secondes))
    return chemin


class DureeTests(unittest.TestCase):
    def test_an_unknown_duration_stays_silent(self):
        """`None` et non « 0 min » : une durée qu'on n'a pas su mesurer ne s'affiche pas."""
        self.assertIsNone(duree(None))

    def test_a_short_summary_is_not_rounded_to_zero(self):
        self.assertEqual("moins d'1 min", duree(12))

    def test_minutes_are_rounded(self):
        self.assertEqual("5 min", duree(295))
        self.assertEqual("1 min", duree(50))

    def test_an_hour_reads_as_an_hour(self):
        self.assertEqual("1 h 12", duree(72 * 60))


class DateTests(unittest.TestCase):
    def test_the_day_is_written_out_in_french(self):
        """Sans `locale` : elle n'est installée ni dans l'image Docker ni sous Windows."""
        self.assertEqual("jeudi 27 août 2026", date_longue(JOUR))

    def test_the_first_of_the_month_is_an_ordinal(self):
        self.assertEqual("mardi 1er septembre 2026", date_longue(dt.date(2026, 9, 1)))


class EnteteTests(unittest.TestCase):
    def test_the_subject_carries_the_date_and_the_listening_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = Lettre.compose(
                JOUR,
                [digest(audio=wav(tmpdir, 120)), digest(categorie="Réglementaire")],
                generated_at=COMPOSEE_LE,
            )

            # Pas de décompte de catégories : l'objet se fait couper par le client
            # avant d'être lu, et le décompte ne change pas la décision d'ouvrir.
            self.assertEqual("Veille du 27 août 2026, 2 min d'écoute", lettre.subject)

    def test_a_day_without_any_category_says_so(self):
        lettre = Lettre.compose(JOUR, [], generated_at=COMPOSEE_LE)

        self.assertEqual("Veille du 27 août 2026, aucun article", lettre.subject)
        self.assertIn("Aucun article trouvé", lettre.text)
        self.assertIn("Aucun article trouvé", lettre.html)

    def test_the_subtitle_counts_what_speaks_over_what_was_collected(self):
        """Deux catégories sur six qui parlent, ce n'est pas une journée pleine."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(retenus=[("A", "https://x.test/a")]),
                digest(categorie="Réglementaire"),
                digest(categorie="Marché"),
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertEqual(1, lettre.racontees)
        self.assertIn("1/3 catégories", lettre.text)
        self.assertIn("1/3 catégories", lettre.html)
        # L'objet, lui, ne le porte pas : il reste court.
        self.assertNotIn("1/3", lettre.subject)

    def test_a_lone_category_stays_singular(self):
        lettre = Lettre.compose(
            JOUR, [digest(retenus=[("A", "https://x.test/a")])], generated_at=COMPOSEE_LE
        )

        self.assertIn("1/1 catégorie ", lettre.text)

    def test_a_category_without_any_retained_article_does_not_count_as_spoken(self):
        """Son texte est une phrase d'explication, pas un résumé."""
        lettre = Lettre.compose(
            JOUR,
            [digest(resume="Aucun article retenu aujourd'hui dans la catégorie Cyber.")],
            generated_at=COMPOSEE_LE,
        )

        self.assertEqual(0, lettre.racontees)
        self.assertIn("0/1 catégorie", lettre.text)

    def test_the_title_sits_outside_the_navy_band(self):
        """Posé sur le fond de la page, il se lit comme le nom du message."""
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        avant_bandeau, bandeau = lettre.html.split("background:#0f1b33;border-radius:10px", 1)
        self.assertIn("<h1", avant_bandeau)
        self.assertIn("Veille du 27 août 2026", avant_bandeau)
        # Le bandeau ne porte plus que ce qui décrit la livraison du jour.
        self.assertNotIn("<h1", bandeau.split("</td></tr>")[0])

    def test_the_subtitle_counts_the_categories_and_details_each_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = Lettre.compose(JOUR, [digest(audio=wav(tmpdir, 180))], generated_at=COMPOSEE_LE)

            self.assertIn("1 catégorie · 3 min d'écoute", lettre.text)
            self.assertIn("Cyber 3 min", lettre.text)
            # En HTML, le détail est à la fois en info-bulle et en pastille : l'attribut
            # `title` ne survit ni au téléphone ni à la plupart des clients mail.
            self.assertIn('title="Cyber 3 min"', lettre.html)
            self.assertIn("Cyber · 3 min", lettre.html)

    def test_a_category_without_audio_has_no_listening_time(self):
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        self.assertIn("1 catégorie", lettre.text)
        self.assertNotIn("min", lettre.subject)
        self.assertNotIn("title=", lettre.html)


class IntroductionTests(unittest.TestCase):
    def test_the_introduction_is_cut_where_we_decided_not_where_the_width_falls(self):
        """D'un seul tenant, le retour tombait au milieu de la date sur un téléphone."""
        lettre = Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE)

        self.assertEqual(
            ["Vendredi 28 août 2026, saint Augustin.", "1991, le Web est présenté publiquement."],
            lettre._introduction,
        )
        # Deux blocs distincts en HTML, et non un paragraphe coupé d'un `<br>` : c'est
        # ce qui laisse chaque ligne se replier pour son compte sur un écran étroit.
        introduction = lettre.html.split("<td style=\"padding:20px 4px 22px;\">")[1].split("</td>")[0]
        self.assertEqual(2, introduction.count("<p style="))
        self.assertNotIn("<br>", introduction)

    def test_the_date_itself_never_breaks(self):
        """« 28 août » séparé de « 2026 » se lit comme une erreur de composition."""
        lettre = Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE)

        self.assertIn("Vendredi&nbsp;28&nbsp;août&nbsp;2026,", lettre.html)
        # La fête reste sécable : liée, « sainte Thérèse de l'Enfant-Jésus » déborderait.
        self.assertIn("saint Augustin", lettre.html)

    def test_the_introduction_opens_on_the_sending_day_not_the_day_covered(self):
        """Le passage de 7 h raconte la veille : ouvrir sur `day` daterait la lettre d'hier."""
        lettre = Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE)

        self.assertIn("Vendredi 28 août 2026", lettre.text)
        self.assertNotIn("Jeudi 27 août 2026", lettre.text)
        # Le titre, lui, garde la date du contenu : c'est ce qu'il nomme.
        self.assertIn("VEILLE DU 27 AOÛT 2026", lettre.text)

    def test_the_feast_follows_the_date_in_apposition(self):
        lettre = Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE)

        # Deux lignes, et la coupure est celle qu'on a choisie.
        attendu = "Vendredi 28 août 2026, saint Augustin.\n1991, le Web est présenté publiquement."
        self.assertIn(attendu, lettre.text)
        self.assertIn("Vendredi&nbsp;28&nbsp;août&nbsp;2026, saint Augustin.", lettre.html)

    def test_a_civil_holiday_reads_the_same_way(self):
        """« la Toussaint », « Noël » : la tournure ne change pas de forme."""
        lettre = Lettre.compose(
            JOUR, [digest()], ephem(jour=dt.date(2026, 11, 1)), generated_at=COMPOSEE_LE
        )

        self.assertIn("Dimanche 1er novembre 2026, la Toussaint.", lettre.text)
        self.assertIn("Dimanche&nbsp;1er&nbsp;novembre&nbsp;2026, la Toussaint.", lettre.html)

    def test_without_an_ephemeride_the_composition_day_stands_alone(self):
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        self.assertIn("Vendredi 28 août 2026.", lettre.text)

    def test_the_sending_day_comes_from_the_ephemeride(self):
        """Une seule source : la fête et le fait doivent parler de la même date que l'ouverture."""
        lettre = Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE)

        self.assertEqual(ENVOI, lettre.sent_on)
        self.assertEqual(JOUR, lettre.day)


class SectionTests(unittest.TestCase):
    def test_both_link_lists_appear_under_their_own_heading(self):
        lettre = Lettre.compose(
            JOUR,
            [
                digest(
                    retenus=[("Faille FortiOS", "https://x.test/a")],
                    veille=[("Rapport de tendances", "https://x.test/b")],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertIn("À lire :", lettre.text)
        self.assertIn("https://x.test/a", lettre.text)
        self.assertIn("À surveiller :", lettre.text)
        self.assertIn("https://x.test/b", lettre.text)
        self.assertIn('href="https://x.test/a"', lettre.html)
        self.assertIn('href="https://x.test/b"', lettre.html)

    def test_an_empty_list_leaves_no_empty_heading(self):
        lettre = Lettre.compose(
            JOUR, [digest(retenus=[("Seul", "https://x.test/a")])], generated_at=COMPOSEE_LE
        )

        self.assertIn("À lire :", lettre.text)
        self.assertNotIn("À surveiller", lettre.text)
        self.assertNotIn("À surveiller", lettre.html)

    def test_the_retained_links_are_laid_into_the_summary_text(self):
        """Le lien est sur le mot qui le rappelle, là où le résumé en parle."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(
                    resume="Une faille critique touche Traefik ce matin.",
                    retenus=[("Multiples vulnérabilités dans Traefik", "https://x.test/a")],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertIn('<a href="https://x.test/a"', lettre.html)
        self.assertIn(">Traefik</a>", lettre.html)
        # Le texte, lui, n'est pas touché : c'est celui que la voix a lu.
        self.assertIn("Une faille critique touche Traefik ce matin.", lettre.text)
        self.assertNotIn("<a", lettre.text)

    def test_only_the_retained_articles_are_laid_into_the_text(self):
        """La liste de veille reste une liste : le résumé n'a pas parlé de ces articles."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(
                    resume="Il est question de Traefik et de CPython.",
                    retenus=[("Faille dans Traefik", "https://x.test/retenu")],
                    veille=[("Faille dans CPython", "https://x.test/veille")],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        # Le paragraphe du résumé seul : les deux listes de liens viennent après.
        resume = lettre.html.split("<div style=\"margin:18px 0 0;\">")[0]
        self.assertIn("https://x.test/retenu", resume)
        self.assertNotIn("https://x.test/veille", resume)
        # L'article de veille reste joignable, mais dans sa liste, pas dans le texte.
        self.assertIn("https://x.test/veille", lettre.html)

    def test_an_article_the_summary_never_names_keeps_its_place_in_the_list(self):
        lettre = Lettre.compose(
            JOUR,
            [digest(resume="Le résumé ne cite rien.", retenus=[("Traefik", "https://x.test/a")])],
            generated_at=COMPOSEE_LE,
        )

        self.assertIn("https://x.test/a", lettre.html)
        self.assertIn("À lire :", lettre.text)

    def test_the_summary_keeps_its_paragraphs(self):
        lettre = Lettre.compose(
            JOUR, [digest(resume="Premier bloc.\n\nSecond bloc.")], generated_at=COMPOSEE_LE
        )

        self.assertEqual(2, lettre.html.count("<p style=\"margin:0 0 14px"))

    def test_a_feed_cannot_inject_markup(self):
        """Titres et sources viennent des flux : ils sont hostiles par défaut."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(
                    resume='Un <script>alert("x")</script> dans le résumé.',
                    retenus=[('<img onerror="x">', "https://x.test/a\">")],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertNotIn("<script>", lettre.html)
        self.assertNotIn("<img onerror", lettre.html)
        self.assertIn("&lt;script&gt;", lettre.html)


class OrdreSectionsTests(unittest.TestCase):
    """Les sections de la lettre suivent le tri naturel de leur catégorie.

    Le site relit cette même lettre pour afficher la journée : si l'email classait
    « 11 » avant « 2 », la page et la lettre montreraient deux ordres différents.
    """

    def test_sections_follow_the_natural_order_of_their_category(self):
        lettre = Lettre.compose(
            JOUR,
            [
                digest(categorie="Cybersécurité"),
                digest(categorie="11 - Veille"),
                digest(categorie="2 - Alertes"),
                digest(categorie="1 - Annonces"),
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertEqual(
            ["1 - Annonces", "2 - Alertes", "11 - Veille", "Cybersécurité"],
            [section.category for section in lettre.sections],
        )

    def test_the_rendered_letter_keeps_that_order(self):
        """L'ordre des sections du rendu est celui du tri, en texte comme en HTML."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(categorie="11 - Veille", resume="Le veille."),
                digest(categorie="2 - Alertes", resume="Les alertes."),
            ],
            generated_at=COMPOSEE_LE,
        )

        positions_texte = [lettre.text.index("2 - ALERTES"), lettre.text.index("11 - VEILLE")]
        positions_html = [lettre.html.index("2 - Alertes"), lettre.html.index("11 - Veille")]

        self.assertLess(*positions_texte)
        self.assertLess(*positions_html)


class LienSurTests(unittest.TestCase):
    """Un flux choisit l'URL de ses articles : seule une page web devient un lien."""

    RESUME = "Une faille critique touche Traefik ce matin."

    def _lettre(self, url):
        return Lettre.compose(
            JOUR,
            [
                digest(
                    resume=self.RESUME,
                    retenus=[("Multiples vulnérabilités dans Traefik", url)],
                    veille=[("Rapport de tendances", url)],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

    def test_a_hostile_or_hostless_url_leaves_the_title_without_a_link(self):
        """En HTML comme en texte : un client mail rend cliquable une URL nue aussi."""
        for url in (
            "javascript:alert(1)",
            " JavaScript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "https:///sans-hote",
            "//exemple.test/sans-schema",
        ):
            with self.subTest(url=url):
                lettre = self._lettre(url)

                for rendu in (lettre.html, lettre.text):
                    self.assertNotIn(url.strip(), rendu)
                    self.assertNotIn(url.strip().replace("<", "&lt;").replace(">", "&gt;"), rendu)
                    self.assertIn("Multiples vulnérabilités dans Traefik", rendu)
                    self.assertIn("Rapport de tendances", rendu)
                self.assertNotIn("<a href", lettre.html)
                # L'ancre du résumé saute aussi : le groupe de mots reste, sans lien.
                self.assertIn(self.RESUME, lettre.html)
                self.assertIn("- Multiples vulnérabilités dans Traefik (Flux A)\n", lettre.text)

    def test_a_refused_article_cannot_steal_the_anchor_of_a_sound_one(self):
        """Écarté avant l'ancrage : le premier servi ne doit pas être un lien qui saute."""
        lettre = Lettre.compose(
            JOUR,
            [
                digest(
                    resume=self.RESUME,
                    retenus=[
                        ("Faille dans Traefik", "javascript:alert(1)"),
                        ("Mise à jour de Traefik", "https://x.test/sain"),
                    ],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertIn('<a href="https://x.test/sain" ', lettre.html)
        self.assertIn(">Traefik</a>", lettre.html)
        self.assertNotIn("javascript:", lettre.html)

    def test_an_url_hiding_a_second_line_is_refused(self):
        """`urlsplit` ignore le saut de ligne ; le texte rendu, lui, le garderait."""
        url = "https://a.test/x\n  javascript:alert(1)"
        lettre = self._lettre(url)

        for rendu in (lettre.html, lettre.text):
            self.assertNotIn("javascript:", rendu)
            self.assertNotIn("https://a.test/x", rendu)
            self.assertIn("Multiples vulnérabilités dans Traefik", rendu)

    def test_a_title_or_source_cannot_add_a_line_to_the_text_version(self):
        lettre = Lettre.compose(
            JOUR,
            [
                CategoryDigest(
                    category="Cyber",
                    articles=[],
                    summary_text="Le résumé.",
                    selected=[
                        dataclasses.replace(
                            article("Titre\nhttps://piege.test/titre", "https://x.test/a"),
                            feed_title="Flux\r\n  https://piege.test/source",
                        )
                    ],
                    watchlist=[],
                )
            ],
            generated_at=COMPOSEE_LE,
        )

        self.assertIn(
            "- Titre https://piege.test/titre (Flux https://piege.test/source)\n  https://x.test/a",
            lettre.text,
        )
        for ligne in lettre.text.splitlines():
            self.assertFalse(ligne.strip().startswith("https://piege.test"), ligne)

    def test_a_web_url_keeps_its_link(self):
        for url in ("https://x.test/a", "http://x.test/a"):
            with self.subTest(url=url):
                lettre = self._lettre(url)

                self.assertIn(f'<a href="{url}"', lettre.html)
                self.assertIn(">Traefik</a>", lettre.html)
                self.assertIn(f"- Multiples vulnérabilités dans Traefik (Flux A)\n  {url}", lettre.text)
                self.assertIn(f"- Rapport de tendances (Flux A)\n  {url}", lettre.text)


class PiedTests(unittest.TestCase):
    def test_the_footer_counts_what_the_letter_carries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = Lettre.compose(
                JOUR,
                [
                    digest(
                        retenus=[("A", "https://x.test/a"), ("B", "https://x.test/b")],
                        veille=[("C", "https://x.test/c")],
                        audio=wav(tmpdir, 60),
                    )
                ],
                generated_at=COMPOSEE_LE,
            )

            self.assertIn("2 articles retenus · 1 à surveiller", lettre.text)
            self.assertIn("1 résumé audio en pièce jointe.", lettre.text)
            self.assertIn("Composée le 28/08/2026 à 07:30.", lettre.text)

    def test_without_audio_the_footer_says_nothing_about_attachments(self):
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        self.assertNotIn("pièce jointe", lettre.text)


class AttachementTests(unittest.TestCase):
    def test_each_section_names_its_own_audio_file(self):
        """Le message porte un mp3 par catégorie : rien ne disait lequel allait avec quoi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = Lettre.compose(
                JOUR, [digest(audio=wav(tmpdir, 60))], generated_at=COMPOSEE_LE
            )

            self.assertIn("Pièce jointe : voix.wav", lettre.text)
            self.assertIn("voix.wav", lettre.html)

    def test_the_file_name_is_never_a_link(self):
        """Aucun client mail n'ouvre une pièce jointe depuis le corps : un lien serait cassé."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = Lettre.compose(
                JOUR, [digest(audio=wav(tmpdir, 60))], generated_at=COMPOSEE_LE
            )

            pied_de_section = lettre.html.split("Pièce jointe")[1].split("</div>")[0]
            self.assertNotIn("<a ", pied_de_section)
            self.assertNotIn("cid:", lettre.html)

    def test_a_category_without_audio_names_nothing(self):
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        self.assertNotIn("Pièce jointe", lettre.text)
        self.assertNotIn("Pièce jointe", lettre.html)

    def test_an_audio_deleted_since_is_not_announced(self):
        """Ce qui n'est pas joint ne doit pas être nommé comme s'il l'était."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = wav(tmpdir, 60)
            chemin.unlink()

            lettre = Lettre.compose(JOUR, [digest(audio=chemin)], generated_at=COMPOSEE_LE)

            # Le chemin est encore là, mais le fichier n'est plus joint : le nom reste
            # cohérent avec la liste des pièces jointes, qui le porte aussi.
            self.assertEqual([chemin], lettre.attachments)

    def test_only_the_categories_with_audio_attach_a_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = wav(tmpdir, 30)
            lettre = Lettre.compose(
                JOUR, [digest(audio=chemin), digest(categorie="Vide")], generated_at=COMPOSEE_LE
            )

            self.assertEqual([chemin], lettre.attachments)


class SectionMesureTests(unittest.TestCase):
    def test_the_listening_time_is_measured_on_the_file_not_estimated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            section = Section.from_digest(digest(audio=wav(tmpdir, 90)))

            self.assertAlmostEqual(90.0, section.secondes, places=2)
            self.assertEqual("2 min", section.ecoute)

    def test_an_audio_deleted_since_leaves_the_time_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = wav(tmpdir, 30)
            chemin.unlink()

            section = Section.from_digest(digest(audio=chemin))

            self.assertIsNone(section.secondes)
            self.assertIsNone(section.ecoute)


class MontageTests(unittest.TestCase):
    """La lettre du mode `global` : un seul fichier, annoncé une seule fois.

    Ce que ces tests protègent : les sections gardent tout ce qui n'est pas l'audio -
    leur texte, leurs ancres, leurs deux listes. L'email doit se lire pareil dans les
    deux modes, à la pièce jointe près."""

    def _lettre(self, tmpdir, secondes=120, sections=2):
        chemin = wav(tmpdir, secondes, nom="journee.wav")
        digests = [
            digest("Cyber", "Une faille sur Traefik.", retenus=[("Traefik", "https://a.test")]),
            digest("Marché", "Un rachat."),
        ][:sections]
        return Lettre.compose(
            JOUR,
            digests,
            ephem(),
            generated_at=COMPOSEE_LE,
            montage=Montage(texte="Bonjour Adrien.", audio_path=chemin),
        )

    def test_the_single_file_is_the_only_attachment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir)

            self.assertEqual(["journee.wav"], [c.name for c in lettre.attachments])

    def test_the_subject_promises_the_time_of_that_one_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir, secondes=120)

            self.assertIn("2 min d'écoute", lettre.subject)

    def test_the_file_is_named_once_above_the_sections(self):
        """Une fois pour la lettre, et non sous chaque catégorie : six fois le même nom
        n'apprendrait rien, et le fichier ne relève d'aucune section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir)

            self.assertEqual(1, lettre.text.count("journee.wav"))
            self.assertIn("Pièce jointe : journee.wav, 2 min", lettre.text)
            self.assertEqual(1, lettre.html.count("journee.wav"))
            # Annoncé avant la première section, pas après.
            self.assertLess(lettre.text.index("journee.wav"), lettre.text.index("CYBER"))

    def test_the_sections_keep_everything_but_their_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir)

            self.assertIn("Une faille sur Traefik.", lettre.text)
            self.assertIn("https://a.test", lettre.text)
            # Aucun badge de durée, aucune pastille : les sections n'ont pas de fichier.
            self.assertEqual([None], list({section.ecoute for section in lettre.sections}))
            self.assertEqual("", lettre._detail_ecoute)

    def test_an_unreadable_file_promises_no_listening_time(self):
        """Comme pour une catégorie : la durée se tait plutôt que d'annoncer « 0 min ».

        Le fichier reste nommé, c'est ce que font déjà les sections, et la lettre n'est
        pas l'endroit qui juge du disque. C'est `runlog.read_montage` qui écarte un audio
        disparu, au renvoi, là où le cas se produit vraiment.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = wav(tmpdir, 60, nom="journee.wav")
            chemin.unlink()
            lettre = Lettre.compose(
                JOUR, [digest()], ephem(), montage=Montage(texte="x", audio_path=chemin)
            )

            self.assertIsNone(lettre.montage_ecoute)
            self.assertIsNone(lettre.total_secondes)
            self.assertIn("Pièce jointe : journee.wav", lettre.text)
            self.assertNotIn("journee.wav -", lettre.text)

    def test_without_a_montage_nothing_changes(self):
        """Le mode par catégorie doit se composer exactement comme avant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = wav(tmpdir, 120)
            lettre = Lettre.compose(JOUR, [digest(audio=chemin)], ephem())

            self.assertEqual(["voix.wav"], [c.name for c in lettre.attachments])
            self.assertIn("Pièce jointe : voix.wav", lettre.text)


SITE = "https://veille.example.com"
LIEN_DESABONNEMENT = f"{SITE}/desabonnement/v1.jeton.signe"


def abonnement(lien=LIEN_DESABONNEMENT, username="bea"):
    return Abonnement(expediteur="La Veille", site_url=SITE, username=username, lien_desabonnement=lien)


class AbonnementPiedTests(unittest.TestCase):
    """Le pied d'une lettre qu'un inconnu reçoit : qui écrit, pourquoi, et comment arrêter.

    Ce que ces tests protègent : les deux rendus portent les mêmes mentions et les mêmes
    liens, et un nom de profil n'entre jamais brut dans le balisage."""

    def _lettre(self, digests=None, **kwargs):
        return Lettre.compose(
            JOUR,
            [digest()] if digests is None else digests,
            generated_at=COMPOSEE_LE,
            abonnement=abonnement(**kwargs),
        )

    def test_the_footer_says_who_sends_and_why_in_both_renderings(self):
        lettre = self._lettre()

        for rendu in (lettre.text, lettre.html):
            self.assertIn(f"Envoyée par La Veille, {SITE}.", rendu)
            self.assertIn("destinataire du profil « bea »", rendu)

    def test_the_three_links_are_in_both_renderings(self):
        lettre = self._lettre()

        for libelle, url in (
            ("Mes résumés", f"{SITE}/resumes"),
            ("Modifier mon profil", f"{SITE}/profil"),
            ("Se désabonner", LIEN_DESABONNEMENT),
        ):
            # Une URL par ligne en texte : c'est ce qu'un client texte rend cliquable.
            self.assertIn(f"\n{libelle} : {url}\n", lettre.text + "\n")
            self.assertIn(f'href="{url}"', lettre.html)
            self.assertIn(f">{libelle}</a>", lettre.html)

    def test_the_links_and_the_username_are_escaped_in_html(self):
        lettre = self._lettre(lien=f"{SITE}/desabonnement/a\"b&c", username="<b>")

        self.assertIn('href="https://veille.example.com/desabonnement/a&quot;b&amp;c"', lettre.html)
        self.assertNotIn("<b>", lettre.html)
        self.assertIn("&lt;b&gt;", lettre.html)

    def test_without_a_signed_link_the_other_links_remain(self):
        lettre = self._lettre(lien=None)

        self.assertIn(f"{SITE}/profil", lettre.text)
        self.assertNotIn("Se désabonner", lettre.text)
        self.assertNotIn("Se désabonner", lettre.html)

    def test_without_a_subscription_the_footer_has_no_link(self):
        """Le site montre la même lettre : il n'a pas à se renvoyer à lui-même."""
        lettre = Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE)

        self.assertNotIn("Envoyée par", lettre.text)
        self.assertNotIn("Envoyée par", lettre.html)
        self.assertNotIn("<a href", lettre.html.split("Composée le")[1])

    def test_the_letter_hands_its_unsubscribe_link_to_the_sender(self):
        expediteur = FakeEmailSender()

        self._lettre().envoyer(expediteur)
        Lettre.compose(JOUR, [digest()], generated_at=COMPOSEE_LE).envoyer(expediteur)

        self.assertEqual([LIEN_DESABONNEMENT, None], expediteur.desabonnements)
        sujet, corps, _, html = expediteur.messages[0]
        self.assertIn("Se désabonner", corps)
        self.assertIn("Se désabonner", html)


class LettreVideTests(unittest.TestCase):
    """La lettre « aucun article » part chez les mêmes lecteurs que les autres."""

    def test_the_date_is_written_out(self):
        lettre = Lettre.compose(dt.date(2026, 8, 29), [], generated_at=COMPOSEE_LE)

        for rendu in (lettre.text, lettre.html):
            self.assertIn("Aucun article trouvé pour le samedi 29 août 2026.", rendu)
            self.assertNotIn("2026-08-29", rendu)

    def test_the_text_version_carries_the_footer(self):
        lettre = Lettre.compose(JOUR, [], generated_at=COMPOSEE_LE, abonnement=abonnement())

        self.assertIn("Composée le 28/08/2026 à 07:30.", lettre.text)
        self.assertIn(f"Se désabonner : {LIEN_DESABONNEMENT}", lettre.text)
        self.assertIn(f'href="{LIEN_DESABONNEMENT}"', lettre.html)


class AbonnementDepuisConfigTests(unittest.TestCase):
    """Le seul constructeur de l'abonnement, partagé par le passage du jour et le renvoi."""

    def _config(self, tmpdir, **surcharges):
        return dataclasses.replace(
            make_config(tmpdir),
            **{
                "site_url": SITE,
                "cle_signature": "k" * 48,
                "username": "bea",
                "profil_id": "0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71",
                "smtp_from": "La Veille <veille@example.com>",
                **surcharges,
            },
        )

    def test_a_complete_configuration_signs_the_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._config(tmpdir)

            abonne = Abonnement.depuis_config(config)

            self.assertEqual("La Veille", abonne.expediteur)
            self.assertEqual("bea", abonne.username)
            self.assertTrue(abonne.lien_desabonnement.startswith(f"{SITE}/desabonnement/v1."))
            demande = Desabonnement(Signataire("k" * 48, OBJET_DESABONNEMENT)).lire(
                abonne.lien_desabonnement.rsplit("/", 1)[1]
            )
            self.assertEqual(config.profil_id, demande.profil_id)
            self.assertTrue(demande.concerne(config.smtp_to))

    def test_without_a_site_or_a_person_there_is_no_subscription(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(Abonnement.depuis_config(self._config(tmpdir, site_url=None)))
            self.assertIsNone(Abonnement.depuis_config(self._config(tmpdir, username="")))

    def test_without_a_key_an_id_or_recipients_there_is_no_unsubscribe_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for surcharge in ({"cle_signature": None}, {"profil_id": ""}, {"smtp_to": []}):
                with self.subTest(surcharge=surcharge):
                    abonne = Abonnement.depuis_config(self._config(tmpdir, **surcharge))
                    self.assertIsNone(abonne.lien_desabonnement)
                    self.assertEqual(f"{SITE}/profil", abonne.lien_profil)

    def test_a_sender_without_display_name_signs_with_the_service_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            abonne = Abonnement.depuis_config(self._config(tmpdir, smtp_from="veille@example.com"))

            self.assertEqual(NOM_SERVICE, abonne.expediteur)


class LiensAvisTests(unittest.TestCase):
    """« Utile » et « Pas utile » au pied : signés pour le profil et la journée racontée.

    Ce que ces tests protègent : les deux rendus portent la question et les deux liens tels
    qu'ils partent, URL en clair en texte, ancres en HTML, le jeton désigne la journée du
    titre et non le jour de l'envoi, et une lettre sans clé ou sans abonnement n'en a pas."""

    PROFIL_ID = "0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71"

    def _abonnement(self, tmpdir, **surcharges):
        config = dataclasses.replace(
            make_config(tmpdir),
            **{
                "site_url": SITE,
                "cle_signature": "k" * 48,
                "username": "bea",
                "profil_id": self.PROFIL_ID,
                **surcharges,
            },
        )
        return Abonnement.depuis_config(config)

    def _lettre(self, tmpdir, digests=None, **surcharges):
        return Lettre.compose(
            JOUR,
            [digest()] if digests is None else digests,
            ephem(),
            generated_at=COMPOSEE_LE,
            abonnement=self._abonnement(tmpdir, **surcharges),
        )

    @staticmethod
    def _liens(texte):
        return re.findall(r"https://veille\.example\.com/retour/[^\s\"<]+", texte)

    def test_the_question_and_both_links_are_in_both_renderings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir)

        utile, pas_utile = self._liens(lettre.text)
        self.assertTrue(utile.endswith("?avis=utile"))
        self.assertTrue(pas_utile.endswith("?avis=pas_utile"))
        self.assertEqual(utile.split("?")[0], pas_utile.split("?")[0])
        # En texte : la question, puis une URL entière par ligne, ce qu'un client texte rend cliquable.
        self.assertIn(
            f"\n{QUESTION_AVIS}\nUtile : {utile}\nPas utile : {pas_utile}\n", lettre.text
        )
        # En HTML : la même question, et deux ancres sur les mêmes URL.
        self.assertIn(QUESTION_AVIS, lettre.html)
        self.assertIn(f'href="{utile}" style="color:#6b7280;text-decoration:underline;">Utile</a>', lettre.html)
        self.assertIn(f'href="{pas_utile}" style="color:#6b7280;text-decoration:underline;">Pas utile</a>', lettre.html)

    def test_the_token_names_the_day_told_not_the_day_sent(self):
        """Le titre dit « Veille du 27 août », la lettre part le 28 : c'est le 27 qu'on juge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir)

        self.assertNotEqual(lettre.day, lettre.sent_on)
        jeton = self._liens(lettre.text)[0].rsplit("/", 1)[1].split("?")[0]
        visee = LienRetour(Signataire("k" * 48, OBJET_RETOUR)).lire(jeton)
        self.assertEqual((self.PROFIL_ID, JOUR), (visee.profil_id, visee.jour))

    def test_recipients_are_not_required(self):
        """Le jeton ne porte pas les adresses : une liste vide n'empêche pas de demander l'avis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir, smtp_to=[])

        self.assertEqual(2, len(self._liens(lettre.text)))
        self.assertNotIn("Se désabonner", lettre.text)

    def test_without_a_key_an_id_or_a_subscription_there_is_no_vote_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettres = [
                self._lettre(tmpdir, cle_signature=None),
                self._lettre(tmpdir, profil_id=""),
                Lettre.compose(JOUR, [digest()], ephem(), generated_at=COMPOSEE_LE),
            ]
        for lettre in lettres:
            for rendu in (lettre.text, lettre.html):
                self.assertNotIn("/retour/", rendu)
                self.assertNotIn(QUESTION_AVIS, rendu)

    def test_the_empty_letter_carries_them_too(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lettre = self._lettre(tmpdir, digests=[])

        self.assertEqual(2, len(self._liens(lettre.text)))
        self.assertIn(QUESTION_AVIS, lettre.html)
        self.assertEqual(2, len(self._liens(lettre.html)))

    def test_only_the_unsubscribe_link_goes_to_the_sender(self):
        """`List-Unsubscribe` reste le seul en-tête : les liens de vote ne vivent que dans le corps."""
        expediteur = FakeEmailSender()
        with tempfile.TemporaryDirectory() as tmpdir:
            self._lettre(tmpdir).envoyer(expediteur)

        self.assertTrue(expediteur.desabonnements[0].startswith(f"{SITE}/desabonnement/"))


if __name__ == "__main__":
    unittest.main()
