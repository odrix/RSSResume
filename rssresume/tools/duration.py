"""Durée d'un fichier audio, lue dans le fichier lui-même.

Le sous-titre de l'email annonce un temps d'écoute par catégorie. L'estimer depuis le
nombre de mots du résumé se trompait de dix à vingt pour cent selon la voix du
fournisseur — un « 3 min » affiché sur quatre minutes trente est pire qu'un temps absent,
puisqu'il sert justement à décider si on lance l'écoute maintenant.

Deux formats à lire, parce que c'est ce que le projet écrit : le `.wav` d'`espeak`, que
la bibliothèque standard sait ouvrir, et le `.mp3` des fournisseurs, qu'elle ne sait pas.
Un format inconnu rend `None`, jamais une exception : une durée manquante retire une
mention du sous-titre, elle ne doit pas empêcher l'envoi du digest.
"""

from __future__ import annotations

import pathlib
import wave

#: En-tête de trame MPEG audio : onze bits de synchronisation.
_SYNC = 0xFFE0

#: Débits du Layer III, en kbit/s, indexés par le champ `bitrate_index` de l'en-tête.
#: Deux tables : MPEG-1 d'un côté, MPEG-2 et 2.5 de l'autre. L'index 0 (libre) et
#: l'index 15 (invalide) sont à zéro — une trame qui les porte n'est pas une trame.
_BITRATES_MPEG1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_BITRATES_MPEG2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)

#: Fréquences d'échantillonnage, indexées par le champ `sampling_rate_index`, et rangées
#: par version. L'index 3 est réservé : zéro, donc trame refusée.
_SAMPLE_RATES = {
    3: (44100, 48000, 32000, 0),  # MPEG-1
    2: (22050, 24000, 16000, 0),  # MPEG-2
    0: (11025, 12000, 8000, 0),  # MPEG-2.5
}

#: Échantillons par trame en Layer III : MPEG-1 en rend le double des autres.
_SAMPLES_PER_FRAME = {3: 1152, 2: 576, 0: 576}

#: Le seul layer lu ici. Les fournisseurs de synthèse ne rendent que du Layer III, et
#: deviner la longueur d'une trame Layer I ou II demande une autre formule.
_LAYER_III = 1


def seconds(path: pathlib.Path | None) -> float | None:
    """La durée du fichier, en secondes. `None` si elle n'est pas lisible.

    Aucune exception ne sort d'ici : un fichier tronqué, effacé entre l'écriture et
    l'envoi, ou dans un format qu'on ne sait pas lire, vaut une durée inconnue.
    """
    if path is None:
        return None
    lecteur = _LECTEURS.get(path.suffix.lower())
    if lecteur is None:
        return None
    try:
        return lecteur(path)
    # `EOFError` est le cas d'un `.wav` coupé avant la fin de son en-tête : `wave` le
    # signale ainsi et non par une `wave.Error`, ce qui suffisait à faire remonter
    # l'exception jusqu'à l'envoi. Un fichier tronqué est une durée inconnue, rien de plus.
    except (OSError, ValueError, EOFError, wave.Error):
        return None


def _wav(path: pathlib.Path) -> float | None:
    """Le `.wav` d'`espeak` : la bibliothèque standard en donne trames et cadence."""
    with wave.open(str(path), "rb") as fichier:
        cadence = fichier.getframerate()
        return fichier.getnframes() / cadence if cadence else None


def _mp3(path: pathlib.Path) -> float | None:
    """Le `.mp3` d'un fournisseur, mesuré trame par trame.

    Pas de règle de trois sur la taille du fichier : elle suppose un débit constant, que
    rien ne garantit, et compte les tags comme du son. Parcourir les trames donne la
    durée exacte en débit constant comme en débit variable, et un fichier de synthèse
    fait quelques milliers de trames — le parcours est immédiat.
    """
    data = path.read_bytes()
    position = _apres_id3(data)
    duree = 0.0
    trames = 0
    while position + 4 <= len(data):
        trame = _trame(data, position)
        if trame is None:
            if trames:
                # Fin des données audio : tag de queue, octets de bourrage, ou fichier
                # coupé. Ce qui a été lu jusque-là reste juste.
                break
            # Avant la première trame, un octet inattendu n'est qu'un décalage : on
            # cherche la synchronisation plus loin plutôt que de renoncer.
            position += 1
            continue
        longueur, secondes = trame
        duree += secondes
        trames += 1
        position += longueur
    return duree if trames else None


def _apres_id3(data: bytes) -> int:
    """L'offset du son, une fois passé le tag ID3v2 s'il y en a un.

    Le tag est en tête et peut peser plusieurs kilo-octets — une pochette d'album y
    tient. Le chercher trame par trame finirait par trouver une fausse synchronisation
    dans une image.
    """
    if not data.startswith(b"ID3") or len(data) < 10:
        return 0
    # Taille sur quatre octets « synchsafe » : sept bits utiles par octet, le huitième
    # étant toujours nul pour ne jamais ressembler à une synchronisation.
    taille = 0
    for octet in data[6:10]:
        taille = (taille << 7) | (octet & 0x7F)
    return 10 + taille


def _trame(data: bytes, position: int) -> tuple[int, float] | None:
    """(longueur en octets, durée en secondes) de la trame à cette position, ou `None`.

    `None` dès qu'un champ est réservé, libre ou invalide : c'est ce qui distingue une
    vraie trame d'une suite d'octets qui commence par les mêmes onze bits.
    """
    entete = int.from_bytes(data[position : position + 4], "big")
    if (entete >> 16) & _SYNC != _SYNC:
        return None

    version = (entete >> 19) & 0b11
    layer = (entete >> 17) & 0b11
    if layer != _LAYER_III or version not in _SAMPLE_RATES:
        return None

    debit = (_BITRATES_MPEG1 if version == 3 else _BITRATES_MPEG2)[(entete >> 12) & 0b1111]
    cadence = _SAMPLE_RATES[version][(entete >> 10) & 0b11]
    if not debit or not cadence:
        return None

    echantillons = _SAMPLES_PER_FRAME[version]
    bourrage = (entete >> 9) & 0b1
    # Longueur d'une trame : les octets qu'occupe, au débit annoncé, la durée qu'elle
    # couvre. L'octet de bourrage rattrape le reste de la division.
    longueur = (echantillons // 8) * debit * 1000 // cadence + bourrage
    return (longueur, echantillons / cadence) if longueur > 4 else None


#: Extension du fichier, et ce qui sait la mesurer.
_LECTEURS = {".wav": _wav, ".mp3": _mp3}
