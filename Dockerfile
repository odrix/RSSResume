# RSSResume — image d'exécution quotidienne.
#
# Rien à compiler, rien à installer : le projet tourne sur la bibliothèque standard, et
# sa seule dépendance déclarée — `tzdata` — est fournie par Alpine sous forme de base de
# fuseaux système, celle-là même que lit `zoneinfo`. Passer par `apk` plutôt que par
# `pip` évite d'emporter une roue et un gestionnaire de paquets dans le résultat.
#
# Ce qui reste dans l'image : Python, la base de fuseaux, et `rssresume/`.
FROM python:3.14-alpine

# `PYTHONUNBUFFERED` : sans lui, les logs du digest resteraient dans un tampon et
# n'arriveraient dans Dokploy qu'à la fin — or l'exécution dure plusieurs minutes.
# `PYTHONIOENCODING` : le suivi d'exécution est en français, et la locale d'un conteneur
# Alpine ne dit rien de l'encodage — les accents ne doivent pas en dépendre.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    RSSRESUME_OUTPUT_DIR=/data

# `pip` n'a plus rien à faire ici une fois `tzdata` posé : une douzaine de mégaoctets
# de moins, et une surface en moins dans un conteneur qui tourne en continu.
RUN apk add --no-cache tzdata \
    && rm -rf /usr/local/lib/python3.*/site-packages/pip \
              /usr/local/lib/python3.*/site-packages/setuptools \
              /usr/local/lib/python3.*/site-packages/pkg_resources \
              /usr/local/bin/pip*

WORKDIR /app
COPY rssresume ./rssresume

# Les fichiers du jour — audio, journaux — appartiennent au volume, pas à l'image.
RUN adduser -D -u 10001 rssresume && mkdir -p /data && chown rssresume:rssresume /data
USER rssresume
VOLUME ["/data"]

# La boucle quotidienne. Pour une exécution unique : `python -m rssresume [options]`.
CMD ["python", "-m", "rssresume.scheduler"]
