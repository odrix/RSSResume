"""Le fait du jour : ce qui, en histoire de la sécurité, est arrivé à cette date.

Une table de repli, et non la source principale : elle ne couvre que ce qu'on a vérifié,
là où le modèle couvre les 365 jours. Elle prend le relais quand il n'y a pas de clé
d'API, quand l'appel échoue, ou quand le modèle répond qu'il ne sait rien.

Chaque entrée est écrite comme elle paraît dans la lettre : « ANNÉE — ce qui s'est
passé, et pourquoi on s'en souvient. » Elle n'a pas vocation à être complète — une date
absente fait descendre sur le calendrier, qui reste juste. En ajouter une se fait ici,
et nulle part ailleurs.
"""

from __future__ import annotations

import datetime as dt

#: Les dates du domaine, indexées par (mois, jour).
EVENEMENTS: dict[tuple[int, int], str] = {
    (1, 1): "1983 — ARPANET bascule de NCP à TCP/IP en une seule journée. C'est de ce « flag day » que date l'Internet tel qu'il fonctionne encore.",
    (1, 9): "2007 — Steve Jobs présente le premier iPhone au Macworld de San Francisco.",
    (1, 15): "2001 — Wikipédia est mise en ligne. Elle ne devait être que le brouillon ouvert d'une encyclopédie relue par des experts ; c'est le brouillon qui a pris toute la place.",
    (1, 24): "1984 — Apple présente le Macintosh, premier ordinateur grand public à interface graphique et souris.",
    (1, 25): "2003 — le ver SQL Slammer sature l'Internet mondial en moins de quinze minutes, en exploitant une faille de SQL Server corrigée six mois plus tôt.",
    (1, 26): "2004 — le ver MyDoom se propage par courriel et devient le plus rapide jamais observé.",
    (2, 4): "2004 — thefacebook.com ouvre aux étudiants de Harvard.",
    (2, 7): "2000 — début d'une semaine d'attaques par déni de service contre Yahoo!, eBay, CNN et Amazon, menées par un adolescent connu sous le pseudonyme Mafiaboy.",
    (2, 14): "2005 — le nom de domaine youtube.com est enregistré.",
    (3, 12): "1989 — Tim Berners-Lee remet à sa hiérarchie du CERN la note « Information Management: A Proposal », l'acte de naissance du Web.",
    (3, 13): "1986 — Microsoft entre en bourse, quatre ans avant Windows 3.0 et la décennie qui lui donnera le poste de travail de bureau.",
    (4, 1): "1976 — Apple Computer est fondée par Steve Jobs, Steve Wozniak et Ronald Wayne.",
    (4, 4): "1975 — Microsoft est fondée par Bill Gates et Paul Allen.",
    (4, 7): "2014 — Heartbleed (CVE-2014-0160) est rendue publique : une faille d'OpenSSL laissait lire la mémoire de deux serveurs web sur trois.",
    (4, 26): "1999 — le virus CIH, dit Tchernobyl, se déclenche à la date prévue et efface le BIOS de centaines de milliers de machines.",
    (5, 4): "2000 — le ver ILOVEYOU se propage par courriel depuis Manille et touche des millions de postes en quelques heures.",
    (5, 7): "2021 — Colonial Pipeline arrête le plus grand oléoduc des États-Unis après une attaque par rançongiciel, et l'incident devient un dossier de sécurité nationale.",
    (5, 12): "2017 — WannaCry se répand dans plus de cent cinquante pays en exploitant EternalBlue, et paralyse une partie du système de santé britannique.",
    (5, 25): "2018 — le RGPD devient applicable dans toute l'Union européenne.",
    (6, 6): "2013 — la presse révèle le programme PRISM à partir des documents d'Edward Snowden.",
    (6, 27): "2017 — NotPetya part d'une mise à jour piégée d'un logiciel comptable ukrainien et devient la cyberattaque la plus coûteuse jamais recensée.",
    (6, 29): "2007 — le premier iPhone arrive en boutique.",
    (7, 13): "2001 — le ver Code Red exploite une faille d'IIS et infecte plus de trois cent mille serveurs en une journée.",
    (7, 15): "2006 — Twitter ouvre au public. Son format court, hérité d'une contrainte du SMS, deviendra le canal d'alerte par défaut de la communauté sécurité.",
    (7, 19): "2024 — une mise à jour défectueuse de CrowdStrike Falcon met hors service des millions de machines Windows dans le monde, sans qu'aucun attaquant soit en cause.",
    (8, 6): "1991 — Tim Berners-Lee publie sur alt.hypertext la première présentation publique du projet World Wide Web.",
    (8, 9): "1995 — l'introduction en bourse de Netscape ouvre la bulle Internet.",
    (8, 11): "2003 — le ver Blaster exploite une faille RPC de Windows et force Microsoft à repenser son cycle de correctifs.",
    (8, 24): "1995 — Windows 95 sort, et avec lui la pile TCP/IP intégrée qui met l'Internet à portée du grand public — et le poste de travail à portée du réseau.",
    (9, 2): "1969 — le premier nœud ARPANET est mis en service à UCLA : deux machines échangent des paquets, et le réseau commence là.",
    (9, 4): "1998 — Google est fondée, sur un algorithme qui classe les pages d'après les liens qu'elles reçoivent plutôt que d'après les mots qu'elles contiennent.",
    (9, 7): "2017 — Equifax annonce la fuite des données de près de cent cinquante millions de personnes, découverte six semaines plus tôt.",
    (9, 18): "2001 — le ver Nimda se propage par cinq vecteurs différents, une semaine après le 11 septembre.",
    (9, 23): "2008 — le premier téléphone sous Android, le T-Mobile G1, est annoncé.",
    (9, 24): "2014 — Shellshock (CVE-2014-6271) est rendue publique : vingt-cinq ans de bash vulnérables à une variable d'environnement piégée.",
    (10, 4): "2021 — une erreur de configuration BGP retire Facebook, Instagram et WhatsApp de l'Internet pendant six heures.",
    (10, 21): "2016 — le botnet Mirai, constitué d'objets connectés, noie les serveurs DNS de Dyn et rend inaccessible une partie du web américain.",
    (10, 29): "1969 — le premier message est envoyé sur ARPANET, d'UCLA vers Stanford. La machine s'effondre après deux lettres : « LO ».",
    (11, 2): "1988 — le ver Morris paralyse une bonne part d'ARPANET et donne naissance au premier CERT.",
    (11, 9): "2004 — Firefox 1.0 est publié et rouvre la guerre des navigateurs, que la domination d'Internet Explorer avait close depuis des années.",
    (11, 24): "2014 — Sony Pictures découvre ses postes chiffrés et ses données publiées : la première attaque destructrice largement attribuée à un État.",
    (12, 9): "2021 — Log4Shell (CVE-2021-44228) est rendue publique : une ligne de journalisation suffisait à exécuter du code à distance, dans un composant présent presque partout.",
    (12, 13): "2020 — FireEye révèle la compromission de la chaîne de mise à jour de SolarWinds Orion, et avec elle une campagne d'espionnage de plusieurs mois.",
}


def du_jour(day: dt.date) -> str:
    """Le fait retenu pour cette date, chaîne vide si la table n'en a pas."""
    return EVENEMENTS.get((day.month, day.day), "")
