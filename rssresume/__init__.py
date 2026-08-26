"""RSSResume package.

Découpage par thème technique :

- `config`     : configuration lue depuis l'environnement
- `models`     : objets métier (Article, CategoryDigest)
- `protocols`  : contrats des collaborateurs
- `freshrss`   : client de l'API Google Reader de FreshRSS
- `llm`        : transport HTTP vers une API compatible OpenAI
- `summaries`  : génération des résumés textuels
- `audio`      : synthèse vocale
- `mailer`     : envoi de l'email
- `digest`     : orchestration
- `cli`        : arguments, assemblage et point d'entrée
- `console`    : suivi d'exécution affiché dans la console
- `pricing`    : grille de tarifs des modèles et coût d'un appel
- `runlog`     : journal `<categorie>.log.json` par catégorie et par jour
"""

from rssresume.audio import AudioGenerator
from rssresume.cli import build_service, main, parse_args
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.freshrss import FreshRSSClient
from rssresume.mailer import EmailSender
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
