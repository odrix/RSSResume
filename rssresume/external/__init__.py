"""Les systèmes que l'on ne contrôle pas, et les clients qui leur parlent.

- `freshrss` : l'API Google Reader de l'instance FreshRSS — lecture des articles,
  écriture des tags de score, marquage comme lu ;
- `mailer` : le serveur SMTP par lequel part le digest ;
- `mailer_resend` : le même envoi par l'API HTTPS de Resend, pour les hébergeurs qui
  filtrent les ports SMTP en sortie ;
- `mail` : lequel des deux, selon `RSSRESUME_MAIL_TRANSPORT`.

Les fournisseurs de LLM sont eux aussi extérieurs, mais ils ont leur propre paquet :
ils portent assez de logique — réglages, prompts, dialectes — pour ne pas tenir ici.
"""
