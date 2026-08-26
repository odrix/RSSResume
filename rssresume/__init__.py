"""RSSResume package.

Découpage par thème technique :

- `cli`        : arguments, assemblage et point d'entrée
- `config`     : configuration lue depuis l'environnement
- `models`     : objets métier (Article, CategoryDigest)
- `protocols`  : contrats des collaborateurs
- `profil`     : profil de pertinence
- `digest`     : orchestration
- `summaries`  : résumé d'une catégorie, ou repli extractif local
- `audio`      : synthèse vocale
- `pricing`    : grille de tarifs et coût d'un appel
- `runlog`     : journal `<categorie>.log.json` par catégorie et par jour
- `external/`  : FreshRSS et SMTP — ce que l'on ne contrôle pas
- `llm/`       : tout ce qui parle à un modèle (voir `llm/__init__.py`)
- `tools/`     : console, texte, lecture d'un avis de vulnérabilité
"""

from rssresume.audio import AudioGenerator
from rssresume.cli import build_service, main, parse_args
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.external.mailer import EmailSender
from rssresume.models import Article, CategoryDigest
from rssresume.summaries import SummaryGenerator

__all__ = [
    "AppConfig",
    "Article",
    "AudioGenerator",
    "CategoryDigest",
    "DigestService",
    "EmailSender",
    "FreshRSSClient",
    "SummaryGenerator",
    "build_service",
    "main",
    "parse_args",
]
