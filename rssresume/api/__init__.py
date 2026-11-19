"""L'API HTTP des profils et des journées, consommée par le site.

Un second processus, à côté du travailleur quotidien : il édite la base de profils que la
tournée lit (`annuaire_sqlite`), et sert les audios que la tournée a écrits. Il ne lance
aucun digest et n'appelle aucun fournisseur — il ne fait que lire et écrire ce qui est
déjà là.

    python -m rssresume.api                     # servir (défaut)
    python -m rssresume.api importer <chemin>   # migrer des profils JSON vers la base
"""
