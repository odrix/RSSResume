"""Les systèmes que l'on ne contrôle pas, et les clients qui leur parlent.

- `freshrss` : l'API Google Reader de l'instance FreshRSS — lecture des articles,
  écriture des tags de score, marquage comme lu ;
- `mailer` : le serveur SMTP par lequel part le digest.

Les fournisseurs de LLM sont eux aussi extérieurs, mais ils ont leur propre paquet :
ils portent assez de logique — réglages, prompts, dialectes — pour ne pas tenir ici.
"""
