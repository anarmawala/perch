# --- base: install deps once (Node 24) ---
FROM node:24-alpine AS base
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- dev: Vite dev server with HMR (source is bind-mounted by compose.dev) ---
FROM base AS dev
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# --- build: produce the static app ---
FROM base AS build
COPY . .
RUN npm run build

# --- prod: nginx serves the built app and reverse-proxies the API ---
FROM nginx:alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
