"""La lettre : son titre, son sous-titre, son introduction, ses sections, son pied.

Ce que ces tests protègent : les deux rendus doivent dire la même chose. Le HTML porte
la mise en page, le texte reste la seule version qu'un client en texte seul affichera,
et un titre d'article venu d'un flux ne doit jamais s'échapper dans le balisage.
"""

import datetime as dt
import pathlib
import tempfile
import unittest
import wave

from rssresume.ephemeride import fetes
from rssresume.models import Article, CategoryDigest, Ephemeride
from rssresume.newsletter import Lettre, Section, date_longue, duree

#: La journée que la lettre raconte, et celle où elle part : le passage de 7 h résume
#: la veille, donc les deux diffèrent tous les matins. Les tests le reproduisent.
JOUR = dt.date(2026, 8, 27)  # un jeudi — la journée racontée
ENVOI = dt.date(2026, 8, 28)  # un vendredi — le jour où la lettre arrive
COMPOSEE_LE = dt.datetime(2026, 8, 28, 7, 30)


def ephem(texte="1991 — le Web est présenté publiquement.", jour=ENVOI, origine="table"):
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


def wav(dossier, secondes):
    """Un vrai fichier audio, pour que la durée soit mesurée et non simulée."""
    chemin = pathlib.Path(dossier) / "voix.wav"
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
            self.assertEqual("Veille du 27 août 2026 — 2 min d'écoute", lettre.subject)

    def test_a_day_without_any_category_says_so(self):
        lettre = Lettre.compose(JOUR, [], generated_at=COMPOSEE_LE)

        self.assertEqual("Veille du 27 août 2026 — aucun article", lettre.subject)
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
            ["Vendredi 28 août 2026, saint Augustin.", "1991 — le Web est présenté publiquement."],
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
        attendu = "Vendredi 28 août 2026, saint Augustin.\n1991 — le Web est présenté publiquement."
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


if __name__ == "__main__":
    unittest.main()
