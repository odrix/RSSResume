"""Les fournisseurs de LLM : leurs réglages, leurs prompts, leurs dialectes.

    from rssresume import llm
    from rssresume.llm import providers

    resumeur = llm.for_action(providers.DIGEST)   # None si la clé manque
    texte = resumeur.write_digest("Tech", articles)

Le contenu du paquet, du général au particulier :

- `providers` : les réglages non secrets, lus dans `providers.json`, et le choix du
  fournisseur pour chaque action ;
- `prompts` : les prompts, les mêmes chez tous les fournisseurs ;
- `base` : `LLMProvider`, les quatre opérations et le transport ;
- `openai`, `mistral` : ce que chaque dialecte change, et rien d'autre ;
- `processing` : la relecture des réponses du noteur.

Les modules du paquet importent `rssresume.llm.base`, jamais `rssresume.llm` : ce
qui est exporté ici n'existe qu'une fois `base` chargé.
"""

from rssresume.llm.base import (
    LLMError,
    LLMProvider,
    TruncatedResponse,
    adapters,
    build,
    for_action,
)

__all__ = [
    "LLMError",
    "LLMProvider",
    "TruncatedResponse",
    "adapters",
    "build",
    "for_action",
]
