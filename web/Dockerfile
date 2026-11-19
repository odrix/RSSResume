# Site d'administration RSSResume : SvelteKit + adapter-node.
#
# Deux étapes : la construction a besoin des dépendances de développement (Vite, Svelte),
# l'image finale seulement de `build/` et des dépendances d'exécution (@node-rs/argon2,
# dont npm choisit le binaire musl précompilé — aucune chaîne de compilation n'est requise).

FROM node:24-alpine AS construction
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:24-alpine
ENV NODE_ENV=production \
    PORT=3000 \
    DATABASE_PATH=/data-web/comptes.sqlite
WORKDIR /app
COPY --from=construction --chown=root:root /app/package.json ./
COPY --from=construction --chown=root:root /app/node_modules ./node_modules
COPY --from=construction --chown=root:root /app/build ./build
# Le code appartient à root et n'est pas modifiable ; seul le volume des comptes l'est.
RUN mkdir -p /data-web && chown node:node /data-web
USER node
VOLUME /data-web
EXPOSE 3000
# `node:sqlite` est stable dans les faits mais s'annonce expérimental à chaque démarrage.
CMD ["node", "--disable-warning=ExperimentalWarning", "build"]
