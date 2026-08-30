"""La lettre du jour : ce que l'email montre, en HTML comme en texte.

Un seul endroit compose l'email, et il le compose deux fois — une version HTML, qui
porte la mise en page, et une version texte, qui reste lisible partout. Les deux
partent dans le même message : le client choisit celle qu'il sait afficher, et un
lecteur en texte seul reçoit toujours quelque chose de complet.

Ce qu'une lettre porte, dans l'ordre :

    Veille du 30 août 2026                            <- le titre : la date du CONTENU
    6 catégories, 21 min d'écoute                     <- le sous-titre, détaillé en info-bulle
    Dimanche 31 août 2026, saint Aristide. 1991 —…    <- l'introduction : le jour de l'ENVOI
    ┌ Cybersécurité technique — 5 min ──────────────┐
    │ le texte du résumé, celui qu'a lu la voix     │
    │ À lire : les articles retenus                 │
    │ À surveiller : ceux qui ont failli l'être     │
    └───────────────────────────────────────────────┘
    …                                                 <- une section par catégorie
    le pied de page

Deux dates cohabitent, et elles ne sont pas interchangeables. Le titre et l'objet
nomment la journée que la lettre RACONTE ; l'introduction ouvre sur le jour de
l'ENVOI, avec sa fête. Le passage de 7 h résume la veille : les confondre datait la
lettre d'un jour dans la boîte de son lecteur.

La composition est ici et non dans `digest.py` parce qu'elle sert deux chemins : la
journée qu'on vient de produire, et celle qu'on renvoie depuis ses journaux
(`--send-only`). Les deux passent par `Lettre.compose` — deux façons d'écrire le même
email finiraient par ne plus dire pareil, et c'est déjà arrivé une fois.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import pathlib

from rssresume import ancres
from rssresume.models import CategoryDigest, Ephemeride, Link
from rssresume.tools import duration

#: Les jours et les mois en toutes lettres. Écrits ici plutôt que demandés à `locale` :
#: la locale française n'est installée ni dans l'image Docker ni sur un poste Windows,
#: et une date qui bascule en anglais selon la machine est un défaut qu'on ne voit qu'en
#: production.
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

#: En dessous, on n'annonce pas de minutes : « 0 min » se lit comme une erreur, et
#: arrondir vingt secondes à une minute serait faux dans l'autre sens.
SECONDES_MIN = 45

#: Le pied de page ne porte encore rien de particulier — il dit ce que la lettre
#: contient et quand elle a été produite. Ce qui viendra s'ajouter (un lien de
#: désabonnement, une mention de l'installation, un rappel de la configuration) se met
#: ici : c'est la seule chaîne que la mise en page traite comme du texte libre.
NOTE_PIED = ""

#: Nom affiché en titre de la lettre, avant la date.
TITRE = "Veille"


def quantieme(day: dt.date) -> str:
    """`1er` le premier du mois, le nombre nu les autres jours."""
    return "1er" if day.day == 1 else str(day.day)


def date_longue(day: dt.date) -> str:
    """`samedi 30 août 2026`. Sans zéro devant le quantième, comme on l'écrit."""
    return f"{JOURS[day.weekday()]} {quantieme(day)} {MOIS[day.month - 1]} {day.year}"


def date_courte(day: dt.date) -> str:
    """`30 août 2026`, pour le titre et l'objet, où le jour de la semaine encombre."""
    return f"{quantieme(day)} {MOIS[day.month - 1]} {day.year}"


def duree(secondes: float | None) -> str | None:
    """`5 min`, `1 h 12`, ou `moins d'1 min`. `None` quand la durée est inconnue.

    `None` et non `0 min` : une durée qu'on n'a pas su mesurer se tait, elle ne se
    déclare pas nulle. C'est ce qui fait disparaître la mention plutôt que d'afficher
    un chiffre faux.
    """
    if secondes is None:
        return None
    if secondes < SECONDES_MIN:
        return "moins d'1 min"
    minutes = round(secondes / 60) or 1
    heures, reste = divmod(minutes, 60)
    return f"{heures} h {reste:02d}" if heures else f"{minutes} min"


@dataclasses.dataclass(frozen=True)
class Section:
    """Une catégorie, telle que la lettre la présente.

    Objet de lecture et non de calcul : tout y est déjà résolu — la durée est mesurée,
    les liens sont dérivés. Les deux rendus n'ont plus qu'à le parcourir, ce qui est la
    seule façon de garantir qu'ils disent la même chose.
    """

    category: str
    summary_text: str
    #: Les articles que le résumé a racontés, dans son ordre de lecture.
    links: list[Link]
    #: Ceux qui ont failli être retenus : lus, notés, mais sous le seuil.
    watchlist: list[Link]
    audio_path: pathlib.Path | None = None
    #: Durée mesurée de l'audio, `None` si le fichier manque ou n'est pas lisible.
    secondes: float | None = None

    @classmethod
    def from_digest(cls, digest: CategoryDigest) -> "Section":
        return cls(
            category=digest.category,
            summary_text=digest.summary_text,
            links=digest.links,
            watchlist=digest.watchlist_links,
            audio_path=digest.audio_path,
            # Mesurée sur le fichier, et au moment de composer : c'est le seul instant
            # où l'audio est certainement écrit, aussi bien après une exécution qu'au
            # renvoi d'une journée passée.
            secondes=duration.seconds(digest.audio_path),
        )

    @property
    def ecoute(self) -> str | None:
        """Le temps d'écoute affiché, `None` pour une catégorie qui n'a rien à dire."""
        return duree(self.secondes)


@dataclasses.dataclass(frozen=True)
class Lettre:
    """L'email d'une journée, prêt à partir sous ses deux formes."""

    #: La journée que la lettre raconte. C'est elle que le titre et l'objet nomment.
    day: dt.date
    sections: list[Section]
    ephemeride: Ephemeride | None = None
    #: L'heure de composition, dans le pied de page. Passée plutôt que lue à l'affichage :
    #: `text` et `html` doivent rendre deux fois la même chose sur le même objet.
    generated_at: dt.datetime | None = None
    #: Le jour de l'envoi, sur lequel l'introduction s'ouvre. Distinct de `day` tous les
    #: matins, puisque le passage de 7 h raconte la veille.
    sent_on: dt.date | None = None

    @classmethod
    def compose(
        cls,
        day: dt.date,
        digests: list[CategoryDigest],
        ephemeride: Ephemeride | None = None,
        generated_at: dt.datetime | None = None,
    ) -> "Lettre":
        """Compose la lettre. `day` est la journée racontée, pas celle de l'envoi.

        Le jour de l'envoi est celui de l'éphéméride, et non un second paramètre :
        elle porte déjà la fête et le fait de cette date, et les trois doivent parler
        du même jour. Sans éphéméride, c'est le moment de la composition qui fait foi.
        """
        moment = generated_at or dt.datetime.now().astimezone()
        return cls(
            day=day,
            sections=[Section.from_digest(digest) for digest in digests],
            ephemeride=ephemeride,
            generated_at=moment,
            sent_on=ephemeride.jour if ephemeride else moment.date(),
        )

    # -- ce que l'expéditeur demande ----------------------------------------

    @property
    def subject(self) -> str:
        """L'objet : la date, puis ce que la lettre coûte à lire.

        Le nombre de catégories et le temps d'écoute sont dans l'objet parce que c'est
        là qu'ils servent — dans la liste des messages, avant de l'ouvrir, quand on
        décide si on a le temps maintenant.
        """
        if not self.sections:
            return f"{TITRE} du {date_courte(self.day)} — aucun article"
        total = duree(self.total_secondes)
        return f"{TITRE} du {date_courte(self.day)} — {self._decompte}" + (
            f", {total} d'écoute" if total else ""
        )

    @property
    def attachments(self) -> list[pathlib.Path]:
        return [section.audio_path for section in self.sections if section.audio_path]

    # -- les chiffres du sous-titre et du pied ------------------------------

    @property
    def total_secondes(self) -> float | None:
        """La durée cumulée des audios, `None` si aucune n'a pu être mesurée."""
        mesurees = [s.secondes for s in self.sections if s.secondes is not None]
        return sum(mesurees) if mesurees else None

    @property
    def _decompte(self) -> str:
        nombre = len(self.sections)
        return f"{nombre} catégorie{'s' if nombre > 1 else ''}"

    @property
    def _detail_ecoute(self) -> str:
        """Le temps d'écoute catégorie par catégorie, la matière de l'info-bulle."""
        return " · ".join(
            f"{section.category} {section.ecoute}"
            for section in self.sections
            if section.ecoute
        )

    @property
    def _sous_titre(self) -> str:
        total = duree(self.total_secondes)
        return self._decompte + (f" · {total} d'écoute" if total else "")

    @property
    def _introduction(self) -> str:
        """Le jour de l'envoi, sa fête, puis le fait historique quand il y en a un.

        La fête est en apposition derrière la date — « Vendredi 28 août 2026, saint
        Augustin. » — parce que c'est ainsi qu'une page de calendrier se lit, et que la
        tournure marche aussi bien pour un saint que pour la Toussaint ou Noël.
        """
        jour = self.sent_on or self.day
        fete = (self.ephemeride.fete if self.ephemeride else "").strip()
        ouverture = date_longue(jour).capitalize() + (f", {fete}." if fete else ".")
        texte = (self.ephemeride.texte if self.ephemeride else "").strip()
        return f"{ouverture} {texte}" if texte else ouverture

    @property
    def _pied(self) -> list[str]:
        """Les lignes du pied de page, dans l'ordre, déjà décidées mais pas encore mises en forme."""
        retenus = sum(len(section.links) for section in self.sections)
        surveilles = sum(len(section.watchlist) for section in self.sections)
        lignes = [
            f"{self._decompte} · {retenus} article{'s' if retenus > 1 else ''} retenu"
            f"{'s' if retenus > 1 else ''} · {surveilles} à surveiller"
        ]
        if self.attachments:
            nombre = len(self.attachments)
            lignes.append(
                f"{nombre} résumé{'s' if nombre > 1 else ''} audio en pièce"
                f"{'s' if nombre > 1 else ''} jointe{'s' if nombre > 1 else ''}."
            )
        if self.generated_at:
            lignes.append(f"Composée le {self.generated_at.strftime('%d/%m/%Y à %H:%M')}.")
        if NOTE_PIED:
            lignes.append(NOTE_PIED)
        return lignes

    # -- rendu texte ---------------------------------------------------------

    @property
    def text(self) -> str:
        """La lettre en texte seul : le repli, et la seule version que l'audio résume.

        Volontairement pauvre en décor — deux ou trois filets, aucune tentative de
        reproduire la mise en page. Un client texte n'a pas besoin d'un dessin, il a
        besoin que les liens soient sur leur propre ligne et que les titres se voient.
        """
        if not self.sections:
            return (
                f"{TITRE.upper()} DU {date_courte(self.day).upper()}\n\n"
                f"{self._introduction}\n\nAucun article trouvé pour le {self.day.isoformat()}.\n"
            )
        blocs = [
            f"{TITRE.upper()} DU {date_courte(self.day).upper()}",
            self._sous_titre + (f"\n{self._detail_ecoute}" if self._detail_ecoute else ""),
            self._introduction,
        ]
        blocs.extend(self._section_texte(section) for section in self.sections)
        # Le pied est un bloc et non des blocs : ses lignes se suivent, là où les
        # sections respirent. Trois lignes espacées auraient l'air de trois sections.
        blocs.append("-" * 60 + "\n" + "\n".join(self._pied))
        return "\n\n".join(blocs).rstrip() + "\n"

    @staticmethod
    def _section_texte(section: Section) -> str:
        titre = section.category.upper()
        if section.ecoute:
            titre += f" — {section.ecoute}"
        lignes = ["=" * 60, titre]
        # Un résumé vide n'ouvre pas un blanc : les journaux écrits avant que le texte
        # du résumé y soit conservé se renvoient sans lui, et la section n'a alors plus
        # que ses liens à montrer.
        if section.summary_text.strip():
            lignes.extend(["", section.summary_text.strip()])
        for entete, liens in (("À lire :", section.links), ("À surveiller :", section.watchlist)):
            if liens:
                lignes.extend(["", entete])
                lignes.extend(f"- {lien.title} ({lien.source})\n  {lien.url}" for lien in liens)
        return "\n".join(lignes)

    # -- rendu HTML ----------------------------------------------------------

    @property
    def html(self) -> str:
        """La lettre en HTML, styles en ligne : aucun client mail ne lit une feuille externe.

        Largeur bornée, une colonne, pas de flottant ni de grille — ce qui traverse
        Outlook comme Gmail comme un téléphone. Le bloc `<style>` ne sert qu'au mode
        sombre, que les clients qui l'ignorent ignorent sans dommage.
        """
        corps = "\n".join(self._section_html(section) for section in self.sections) or _vide(
            self.day
        )
        return _DOCUMENT.format(
            titre=_e(f"{TITRE} du {date_courte(self.day)}"),
            entete=self._entete_html(),
            introduction=_e(self._introduction),
            sections=corps,
            pied="<br>".join(_e(ligne) for ligne in self._pied),
        )

    def _entete_html(self) -> str:
        """Titre, sous-titre, et le détail des durées — en info-bulle et en pastilles.

        Les deux, et non l'un ou l'autre : l'info-bulle ne survit ni au téléphone ni à
        la plupart des clients mail, les pastilles se lisent partout. L'attribut `title`
        est le supplément de ceux qui survolent, pas le support de l'information.
        """
        detail = self._detail_ecoute
        infobulle = f' title="{_e(detail)}"' if detail else ""
        pastilles = "".join(
            _PASTILLE.format(texte=_e(f"{section.category} · {section.ecoute}"))
            for section in self.sections
            if section.ecoute
        )
        return _ENTETE.format(
            titre=_e(f"{TITRE} du {date_courte(self.day)}"),
            sous_titre=_e(self._sous_titre),
            infobulle=infobulle,
            pastilles=f'<div style="margin-top:14px;line-height:2.1;">{pastilles}</div>'
            if pastilles
            else "",
        )

    @classmethod
    def _section_html(cls, section: Section) -> str:
        badge = (
            _BADGE.format(texte=_e(section.ecoute))
            if section.ecoute
            else ""
        )
        return _SECTION.format(
            categorie=_e(section.category),
            badge=badge,
            # Les liens retenus SEULEMENT : ce sont eux que le résumé raconte, et un
            # article dont il n'a pas parlé n'a aucun mot à quoi s'accrocher.
            resume=_resume_html(section.summary_text, section.links),
            liens=cls._liens_html("À lire", section.links, "#1a4fa0")
            + cls._liens_html("À surveiller", section.watchlist, "#6b7280"),
        )

    @staticmethod
    def _liens_html(entete: str, liens: list[Link], couleur: str) -> str:
        """Une liste de liens sous son en-tête, rien du tout si la liste est vide.

        Les deux listes ont la même forme et deux couleurs : ce qui a été raconté et ce
        qui ne l'a pas été doivent se distinguer d'un coup d'œil, sans qu'on ait à lire
        l'en-tête pour savoir dans laquelle on se trouve.
        """
        if not liens:
            return ""
        items = "".join(
            _LIEN.format(url=_e(lien.url), titre=_e(lien.title), source=_e(lien.source), couleur=couleur)
            for lien in liens
        )
        return _LISTE.format(entete=_e(entete), items=items, couleur=couleur)


# -- gabarits ----------------------------------------------------------------
#
# Des chaînes à trous et non un moteur de gabarits : le HTML d'un email est figé — pas
# de boucle, pas de condition, pas d'héritage — et une dépendance de plus pour six
# blocs ne se justifierait pas. Les styles sont en ligne parce que Gmail supprime tout
# ce qui vit dans un `<style>`, à l'exception notable des requêtes média.


def _e(value: str) -> str:
    """Échappement HTML. Titres et sources viennent des flux : ils sont hostiles par défaut."""
    return html.escape(value or "", quote=True)


def _resume_html(texte: str, liens: list[Link] | None = None) -> str:
    """Le résumé, ses paragraphes en `<p>`, ses retours simples en `<br>`, ses liens posés.

    Le texte vient du modèle et part aussi en synthèse vocale : il est écrit pour être
    lu à voix haute, sans balisage. Sa seule structure est le passage à la ligne, et
    c'est celle-là qu'on transpose.

    Les liens des articles retenus sont posés dessus après coup, sur le groupe de mots
    qui rappelle leur titre (`ancres.py`). Le texte n'est pas modifié d'un caractère —
    la voix lit le même — et l'URL vient de la sélection : un lien mal placé reste un
    lien juste. Ceux qui ne trouvent pas où se poser restent dans la liste « À lire ».
    """
    segments = ancres.ancrer((texte or "").strip(), liens or [])
    return "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.62;color:#1f2937;">'
        f"{''.join(_segment_html(segment) for segment in bloc)}</p>"
        for bloc in _blocs(segments)
    )


def _blocs(segments: list[ancres.Segment]) -> list[list[ancres.Segment]]:
    """Les segments regroupés en paragraphes, sur les lignes vides du texte nu.

    Le découpage en paragraphes vient après l'ancrage et non avant : les liens se
    placent sur le résumé entier, et c'est seulement une fois qu'ils sont placés qu'on
    sait où couper sans passer au travers de l'un d'eux. Un segment qui porte un lien
    n'est jamais coupé — l'ancre ne traverse pas une ligne vide, par construction.
    """
    blocs: list[list[ancres.Segment]] = [[]]
    for segment in segments:
        if segment.url:
            blocs[-1].append(segment)
            continue
        morceaux = segment.texte.split("\n\n")
        blocs[-1].append(ancres.Segment(morceaux[0]))
        blocs.extend([ancres.Segment(morceau)] for morceau in morceaux[1:])
    return [_rogne(bloc) for bloc in blocs if "".join(s.texte for s in bloc).strip()]


def _rogne(bloc: list[ancres.Segment]) -> list[ancres.Segment]:
    """Le paragraphe sans ses blancs de bord, ceux que la coupe vient de laisser."""
    tete, *reste = bloc
    bloc = [dataclasses.replace(tete, texte=tete.texte.lstrip()), *reste] if not tete.url else bloc
    queue = bloc[-1]
    if not queue.url:
        bloc = [*bloc[:-1], dataclasses.replace(queue, texte=queue.texte.rstrip())]
    return [segment for segment in bloc if segment.texte or segment.url]


def _segment_html(segment: ancres.Segment) -> str:
    """Un morceau de résumé, échappé, et enveloppé d'un lien s'il en porte un.

    L'échappement se fait ici et pas avant : le découpage travaille sur le texte brut,
    ce qui lui évite d'avoir à reconnaître une entité HTML au milieu d'un nom propre.
    """
    corps = _e(segment.texte).replace(chr(10), "<br>")
    if not segment.url:
        return corps
    return (
        f'<a href="{_e(segment.url)}" '
        f'style="color:#1a4fa0;text-decoration:underline;'
        f'text-underline-offset:2px;text-decoration-thickness:1px;">{corps}</a>'
    )


def _vide(day: dt.date) -> str:
    return (
        f'<p style="margin:0;padding:28px 0;text-align:center;color:#6b7280;font-size:15px;">'
        f"Aucun article trouvé pour le {_e(day.isoformat())}.</p>"
    )


_PASTILLE = (
    '<span style="display:inline-block;padding:4px 11px;margin:0 6px 0 0;'
    'border:1px solid rgba(255,255,255,0.28);border-radius:999px;'
    'font-size:12px;color:#e8eefc;white-space:nowrap;">{texte}</span>'
)

_BADGE = (
    '<span style="display:inline-block;padding:3px 10px;margin-left:10px;'
    'background:#eef2f9;border-radius:999px;font-size:12px;font-weight:500;'
    'color:#41577f;vertical-align:middle;white-space:nowrap;">{texte}</span>'
)

_LIEN = (
    '<li style="margin:0 0 9px;">'
    '<a href="{url}" style="color:{couleur};text-decoration:none;font-weight:500;">{titre}</a>'
    '<span style="color:#9ca3af;font-size:13px;"> — {source}</span>'
    "</li>"
)

_LISTE = (
    '<div style="margin:18px 0 0;">'
    '<div style="font-size:11px;font-weight:700;letter-spacing:0.09em;'
    'text-transform:uppercase;color:{couleur};margin-bottom:9px;">{entete}</div>'
    '<ul style="margin:0;padding-left:19px;font-size:14px;line-height:1.5;">{items}</ul>'
    "</div>"
)

_SECTION = """
      <tr><td style="padding:0 0 14px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:#ffffff;border:1px solid #e3e8ef;border-radius:10px;">
          <tr><td style="padding:22px 24px 24px;">
            <h2 style="margin:0 0 14px;font-size:17px;font-weight:600;color:#0f1b33;">
              {categorie}{badge}
            </h2>
            {resume}{liens}
          </td></tr>
        </table>
      </td></tr>"""

_ENTETE = """
      <tr><td style="background:#0f1b33;border-radius:10px;padding:26px 26px 24px;">
        <h1 style="margin:0;font-size:23px;font-weight:600;color:#ffffff;letter-spacing:-0.2px;">
          {titre}
        </h1>
        <div{infobulle} style="margin:7px 0 0;font-size:14px;color:#9fb2d6;">{sous_titre}</div>
        {pastilles}
      </td></tr>"""

_DOCUMENT = """<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{titre}</title>
</head>
<body style="margin:0;padding:0;background:#eef1f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#eef1f6;">
  <tr><td align="center" style="padding:24px 12px 32px;">
    <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"
           style="width:100%;max-width:640px;font-family:-apple-system,BlinkMacSystemFont,
                  'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
{entete}
      <tr><td style="padding:20px 4px 22px;">
        <p style="margin:0;font-size:15px;line-height:1.62;color:#42506b;font-style:italic;">
          {introduction}
        </p>
      </td></tr>
{sections}
      <tr><td style="padding:22px 6px 0;border-top:1px solid #dde3ec;">
        <p style="margin:0;font-size:12px;line-height:1.75;color:#8a93a5;">{pied}</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""
