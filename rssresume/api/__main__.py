"""Point d'entrée de l'API : `servir` (défaut) ou `importer <chemin>`."""

from __future__ import annotations

import argparse
import pathlib

from rssresume.annuaire_sqlite import AnnuaireSqlite
from rssresume.api.importation import Importateur, rendre_compte
from rssresume.api.serveur import ApplicationApi, ServeurApi, adresse_depuis_env
from rssresume.profil import ENV_PROFILES_DB, Annuaire
from rssresume.tools import console


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m rssresume.api", description="RSSResume HTTP API.")
    commandes = parser.add_subparsers(dest="commande")
    commandes.add_parser("servir", help="Serve the API (default).")
    importer = commandes.add_parser(
        "importer",
        help="Import a directory of {username}.json profiles, or a single file, into the database. "
        "Idempotent; source files are left untouched.",
    )
    importer.add_argument("chemin", type=pathlib.Path)
    return parser.parse_args(argv)


def servir() -> int:
    """Lit toute la configuration avant d'ouvrir le port : un jeton absent ou une base non
    déclarée font échouer le conteneur au déploiement, pas la première requête du site."""
    application = ApplicationApi.from_env()
    hote, port = adresse_depuis_env()
    serveur = ServeurApi((hote, port), application)
    console.log(f"API RSSResume : écoute sur {hote}:{serveur.server_address[1]}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


def importer(chemin: pathlib.Path) -> int:
    annuaire = Annuaire.depuis_env()
    if not isinstance(annuaire, AnnuaireSqlite):
        raise ValueError(f"L'import écrit dans la base : poser {ENV_PROFILES_DB}.")
    bilan = Importateur(annuaire).importer(chemin)
    rendre_compte(bilan)
    return 1 if bilan.en_echec else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.commande == "importer":
            return importer(args.chemin)
        return servir()
    except ValueError as exc:
        console.error(f"API RSSResume : {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
