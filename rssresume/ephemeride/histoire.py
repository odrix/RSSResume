"""Le fait du jour : ce qui, en histoire de l'informatique et du numérique, est arrivé à cette date.

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
    (2, 15): "1946 — l'ENIAC est officiellement inauguré à l'université de Pennsylvanie : près de trente tonnes, dix-huit mille tubes, et le premier calculateur électronique généraliste montré au public.",
    (2, 20): "1991 — Guido van Rossum publie la version 0.9.0 de Python sur le forum alt.sources. Le langage pensé pour être lu deviendra celui de l'automatisation, de l'enseignement et de la science des données.",
    (3, 9): "2016 — AlphaGo bat Lee Sedol dans la première partie de leur match à Séoul : le go, qu'on disait hors de portée des machines pour une décennie encore, tombe à son tour.",
    (3, 12): "1989 — Tim Berners-Lee remet à sa hiérarchie du CERN la note « Information Management: A Proposal », l'acte de naissance du Web.",
    (3, 13): "1986 — Microsoft entre en bourse, quatre ans avant Windows 3.0 et la décennie qui lui donnera le poste de travail de bureau.",
    (3, 15): "1985 — symbolics.com devient le premier nom de domaine en .com enregistré, à une époque où presque personne ne savait encore à quoi servirait un nom de domaine.",
    (3, 24): "2001 — Mac OS X 10.0 sort : Apple abandonne son système historique pour une base Unix, celle qui porte encore macOS et, par dérivation, iOS.",
    (4, 1): "1976 — Apple Computer est fondée par Steve Jobs, Steve Wozniak et Ronald Wayne.",
    (4, 3): "1973 — Martin Cooper, de Motorola, passe le premier appel depuis un téléphone portable, dans une rue de New York — à son concurrent des Bell Labs.",
    (4, 4): "1975 — Microsoft est fondée par Bill Gates et Paul Allen.",
    (4, 7): "2014 — Heartbleed (CVE-2014-0160) est rendue publique : une faille d'OpenSSL laissait lire la mémoire de deux serveurs web sur trois.",
    (4, 10): "2008 — GitHub ouvre officiellement. L'hébergement de dépôts Git, et la revue de code par pull request qu'il popularise, deviendront la manière ordinaire de travailler à plusieurs.",
    (4, 19): "1965 — Gordon Moore publie dans Electronics l'article où il prédit le doublement régulier du nombre de composants sur une puce. La « loi de Moore » rythmera l'industrie pendant un demi-siècle.",
    (4, 26): "1999 — le virus CIH, dit Tchernobyl, se déclenche à la date prévue et efface le BIOS de centaines de milliers de machines.",
    (4, 30): "1993 — le CERN verse le logiciel du World Wide Web dans le domaine public. Sans licence ni redevance, le Web pouvait appartenir à tout le monde, et c'est ce qui s'est produit.",
    (5, 4): "2000 — le ver ILOVEYOU se propage par courriel depuis Manille et touche des millions de postes en quelques heures.",
    (5, 7): "2021 — Colonial Pipeline arrête le plus grand oléoduc des États-Unis après une attaque par rançongiciel, et l'incident devient un dossier de sécurité nationale.",
    (5, 11): "1997 — Deep Blue, d'IBM, remporte la sixième et dernière partie de son match contre Garry Kasparov : pour la première fois, un champion du monde d'échecs perd un match face à une machine.",
    (5, 12): "2017 — WannaCry se répand dans plus de cent cinquante pays en exploitant EternalBlue, et paralyse une partie du système de santé britannique.",
    (5, 15): "2015 — Rust 1.0 est publié : un langage système qui garantit la sûreté de la mémoire dès la compilation, sans ramasse-miettes, entre dans la course face à C et C++.",
    (5, 22): "1980 — Pac-Man est testé pour la première fois en salle à Tokyo. Namco y cherchait un jeu capable d'attirer un public que les tirs spatiaux laissaient indifférent.",
    (5, 23): "1995 — Sun présente officiellement Java au salon SunWorld, avec sa promesse : écrire une fois, exécuter partout.",
    (5, 25): "2018 — le RGPD devient applicable dans toute l'Union européenne.",
    (6, 2): "2014 — Apple dévoile Swift à sa conférence des développeurs, pour succéder à Objective-C dans l'écriture des applications de ses plates-formes.",
    (6, 6): "2013 — la presse révèle le programme PRISM à partir des documents d'Edward Snowden.",
    (6, 27): "2017 — NotPetya part d'une mise à jour piégée d'un logiciel comptable ukrainien et devient la cyberattaque la plus coûteuse jamais recensée.",
    (6, 29): "2007 — le premier iPhone arrive en boutique.",
    (7, 13): "2001 — le ver Code Red exploite une faille d'IIS et infecte plus de trois cent mille serveurs en une journée.",
    (7, 15): "2006 — Twitter ouvre au public. Son format court, hérité d'une contrainte du SMS, deviendra le fil d'actualité en temps réel de toute la profession.",
    (7, 18): "1968 — Robert Noyce et Gordon Moore fondent Intel, qui commence par les mémoires avant de donner son nom au microprocesseur du PC.",
    (7, 19): "2024 — une mise à jour défectueuse de CrowdStrike Falcon met hors service des millions de machines Windows dans le monde, sans qu'aucun attaquant soit en cause.",
    (7, 20): "1969 — Apollo 11 se pose sur la Lune malgré les alarmes 1202 de l'ordinateur de guidage, dont le logiciel, conçu par l'équipe de Margaret Hamilton, sacrifie les tâches secondaires pour garder l'essentiel.",
    (8, 6): "1991 — Tim Berners-Lee publie sur alt.hypertext la première présentation publique du projet World Wide Web.",
    (8, 9): "1995 — l'introduction en bourse de Netscape ouvre la bulle Internet.",
    (8, 11): "2003 — le ver Blaster exploite une faille RPC de Windows et force Microsoft à repenser son cycle de correctifs.",
    (8, 12): "1981 — IBM lance l'IBM PC 5150. Son architecture ouverte, vite copiée, fait du « compatible PC » le standard du poste de travail pour des décennies.",
    (8, 24): "1995 — Windows 95 sort, et avec lui la pile TCP/IP intégrée qui met l'Internet à portée du grand public — et le poste de travail à portée du réseau.",
    (8, 25): "1991 — Linus Torvalds annonce sur comp.os.minix un système d'exploitation qui ne serait « qu'un passe-temps, rien de gros ni de professionnel ». Ce sera Linux.",
    (9, 2): "1969 — le premier nœud ARPANET est mis en service à UCLA : deux machines échangent des paquets, et le réseau commence là.",
    (9, 4): "1998 — Google est fondée, sur un algorithme qui classe les pages d'après les liens qu'elles reçoivent plutôt que d'après les mots qu'elles contiennent.",
    (9, 7): "2017 — Equifax annonce la fuite des données de près de cent cinquante millions de personnes, découverte six semaines plus tôt.",
    (9, 9): "1947 — l'équipe du Mark II, à Harvard, trouve un papillon de nuit coincé dans un relais et le colle dans le journal de bord : « premier cas réel de bug trouvé ».",
    (9, 13): "1985 — Super Mario Bros. sort au Japon sur la Famicom et fixe pour longtemps la grammaire du jeu de plates-formes à défilement horizontal.",
    (9, 15): "2008 — Stack Overflow ouvre sa bêta publique. Une génération de développeurs y prendra l'habitude de trouver la réponse avant même d'avoir fini de poser la question.",
    (9, 18): "2001 — le ver Nimda se propage par cinq vecteurs différents, une semaine après le 11 septembre.",
    (9, 23): "2008 — le premier téléphone sous Android, le T-Mobile G1, est annoncé.",
    (9, 24): "2014 — Shellshock (CVE-2014-6271) est rendue publique : vingt-cinq ans de bash vulnérables à une variable d'environnement piégée.",
    (9, 27): "1983 — Richard Stallman annonce le projet GNU : écrire un système d'exploitation compatible Unix entièrement libre. Le mouvement du logiciel libre part de ce message.",
    (10, 4): "2021 — une erreur de configuration BGP retire Facebook, Instagram et WhatsApp de l'Internet pendant six heures.",
    (10, 10): "1994 — Håkon Wium Lie publie la première proposition de feuilles de style en cascade pour le Web. Séparer le fond de la forme deviendra CSS, et un métier à part entière.",
    (10, 18): "1958 — Tennis for Two est présenté sur un oscilloscope aux visiteurs du laboratoire de Brookhaven : l'un des tout premiers jeux vidéo, conçu pour une journée portes ouvertes.",
    (10, 21): "2016 — le botnet Mirai, constitué d'objets connectés, noie les serveurs DNS de Dyn et rend inaccessible une partie du web américain.",
    (10, 28): "2014 — HTML5 devient une recommandation du W3C, et avec lui la vidéo, l'audio et le dessin natifs dans le navigateur, sans greffon.",
    (10, 29): "1969 — le premier message est envoyé sur ARPANET, d'UCLA vers Stanford. La machine s'effondre après deux lettres : « LO ».",
    (11, 2): "1988 — le ver Morris paralyse une bonne part d'ARPANET et donne naissance au premier CERT.",
    (11, 9): "2004 — Firefox 1.0 est publié et rouvre la guerre des navigateurs, que la domination d'Internet Explorer avait close depuis des années.",
    (11, 10): "2009 — Google présente Go, un langage pensé pour compiler vite et écrire simplement des programmes concurrents. Docker et Kubernetes seront écrits avec.",
    (11, 12): "1990 — Tim Berners-Lee et Robert Cailliau publient « WorldWideWeb: Proposal for a HyperText Project », la proposition qui donne au Web son nom et son plan de travail.",
    (11, 15): "1971 — Intel annonce le 4004, premier microprocesseur commercialisé : toute une unité centrale sur une seule puce, conçue au départ pour une calculatrice japonaise.",
    (11, 20): "1985 — Microsoft commercialise Windows 1.0, une interface graphique posée sur MS-DOS. Il faudra attendre la version 3.0 pour qu'elle s'impose.",
    (11, 23): "2004 — World of Warcraft sort en Amérique du Nord et fait du jeu en ligne massivement multijoueur un loisir grand public, à des millions d'abonnés.",
    (11, 24): "2014 — Sony Pictures découvre ses postes chiffrés et ses données publiées : la première attaque destructrice largement attribuée à un État.",
    (11, 29): "1972 — Atari lance Pong, le premier jeu vidéo d'arcade à connaître un succès commercial. Deux raquettes, une balle, et toute une industrie qui démarre.",
    (11, 30): "2022 — OpenAI ouvre ChatGPT au public. En quelques semaines, l'IA générative passe des laboratoires au quotidien de tous les métiers.",
    (12, 3): "1992 — Neil Papworth envoie depuis un ordinateur le premier SMS de l'histoire, « Merry Christmas », vers le téléphone d'un dirigeant de Vodafone.",
    (12, 4): "1995 — Netscape et Sun annoncent JavaScript, un langage de script pour le navigateur. Il finira par tourner partout, serveurs compris.",
    (12, 9): "2021 — Log4Shell (CVE-2021-44228) est rendue publique : une ligne de journalisation suffisait à exécuter du code à distance, dans un composant présent presque partout.",
    (12, 10): "1993 — id Software publie Doom en partagiciel. Le jeu popularise le tir à la première personne, le jeu en réseau local et les modifications faites par les joueurs eux-mêmes.",
    (12, 13): "2020 — FireEye révèle la compromission de la chaîne de mise à jour de SolarWinds Orion, et avec elle une campagne d'espionnage de plusieurs mois.",
    (12, 23): "1947 — John Bardeen et Walter Brattain font la démonstration du premier transistor devant la direction des Bell Labs. Toute l'électronique moderne en descend.",
}


def du_jour(day: dt.date) -> str:
    """Le fait retenu pour cette date, chaîne vide si la table n'en a pas."""
    return EVENEMENTS.get((day.month, day.day), "")
