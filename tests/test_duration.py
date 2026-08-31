"""La mesure du temps d'écoute, lue dans le fichier audio.

Ce que ces tests protègent : le sous-titre de l'email annonce une durée par catégorie.
Une durée fausse est pire qu'une durée absente — elle sert à décider si on lance
l'écoute maintenant — et un fichier illisible ne doit jamais empêcher l'envoi.
"""

import pathlib
import tempfile
import unittest
import wave

from rssresume.tools import duration

#: Un en-tête de trame MPEG-1 Layer III, 128 kbit/s, 44100 Hz, sans bourrage.
#: 0xFF 0xFB : synchronisation, version MPEG-1, layer III.
#: 0x90      : index de débit 9 (128 kbit/s), index de cadence 0 (44100 Hz).
#: 0xC4      : mode mono — le champ ne change ni la longueur ni la durée.
ENTETE_MPEG1 = bytes((0xFF, 0xFB, 0x90, 0xC4))

#: 144 × 128000 / 44100, arrondi à l'entier inférieur : la longueur que le décodeur
#: attend, et donc celle à laquelle la trame suivante commence.
LONGUEUR_TRAME = 417

#: 1152 échantillons à 44100 Hz.
DUREE_TRAME = 1152 / 44100


def mp3(nombre_de_trames, prefixe=b""):
    """Un MP3 de synthèse : `nombre_de_trames` trames identiques, précédées de `prefixe`."""
    trame = ENTETE_MPEG1 + bytes(LONGUEUR_TRAME - len(ENTETE_MPEG1))
    return prefixe + trame * nombre_de_trames


def tag_id3(charge_utile):
    """Un tag ID3v2 de la taille voulue, tel qu'un encodeur en pose en tête de fichier."""
    taille = len(charge_utile)
    # Taille « synchsafe » : sept bits utiles par octet, le huitième toujours nul.
    octets = bytes(((taille >> 21) & 0x7F, (taille >> 14) & 0x7F, (taille >> 7) & 0x7F, taille & 0x7F))
    return b"ID3\x04\x00\x00" + octets + charge_utile


class Mp3Tests(unittest.TestCase):
    def test_a_frame_walk_gives_the_exact_duration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.mp3"
            chemin.write_bytes(mp3(100))

            self.assertAlmostEqual(100 * DUREE_TRAME, duration.seconds(chemin), places=5)

    def test_an_id3_tag_is_skipped_rather_than_scanned(self):
        """Une pochette d'album finirait par offrir une fausse synchronisation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.mp3"
            # Le tag contient l'octet de synchronisation, exprès.
            chemin.write_bytes(mp3(50, prefixe=tag_id3(b"\xff\xfb" * 500)))

            self.assertAlmostEqual(50 * DUREE_TRAME, duration.seconds(chemin), places=5)

    def test_trailing_bytes_do_not_extend_the_duration(self):
        """Un tag de queue n'est pas du son : ce qui a été lu avant reste juste."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.mp3"
            chemin.write_bytes(mp3(20) + b"TAG" + bytes(125))

            self.assertAlmostEqual(20 * DUREE_TRAME, duration.seconds(chemin), places=5)

    def test_a_file_without_a_single_frame_has_no_duration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.mp3"
            chemin.write_bytes(b"ceci n'est pas du son" * 50)

            self.assertIsNone(duration.seconds(chemin))


class ApresId3Tests(unittest.TestCase):
    """`apres_id3` est publique parce qu'`audio.py` s'en sert pour rabouter les morceaux
    d'une synthèse découpée : le tag des reprises doit sauter, sinon le parcours des
    trames s'arrête dessus et la durée annoncée est celle du premier morceau."""

    def test_a_file_without_a_tag_starts_at_zero(self):
        self.assertEqual(0, duration.apres_id3(mp3(3)))

    def test_the_offset_clears_the_whole_tag(self):
        charge = b"pochette" * 10
        self.assertEqual(10 + len(charge), duration.apres_id3(tag_id3(charge)))


class WavTests(unittest.TestCase):
    def test_a_wav_is_read_from_its_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.wav"
            with wave.open(str(chemin), "wb") as fichier:
                fichier.setnchannels(1)
                fichier.setsampwidth(2)
                fichier.setframerate(22050)
                fichier.writeframes(bytes(2 * 22050 * 3))  # trois secondes

            self.assertAlmostEqual(3.0, duration.seconds(chemin), places=3)

    def test_a_truncated_wav_is_an_unknown_duration_not_a_crash(self):
        """`wave` signale un en-tête coupé par une `EOFError`, qui remontait jusqu'à l'envoi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.wav"
            chemin.write_text("du texte, pas du son", encoding="utf-8")

            self.assertIsNone(duration.seconds(chemin))


class ContratTests(unittest.TestCase):
    def test_no_path_no_duration(self):
        self.assertIsNone(duration.seconds(None))

    def test_an_unknown_extension_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "voix.opus"
            chemin.write_bytes(b"peu importe")

            self.assertIsNone(duration.seconds(chemin))

    def test_a_missing_file_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(duration.seconds(pathlib.Path(tmpdir) / "absent.mp3"))


if __name__ == "__main__":
    unittest.main()
