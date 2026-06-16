# syntax=docker/dockerfile:1
# Multi-stage: build the Vite SPA, then serve it via nginx which also reverse-
# proxies the Django-served paths (/api, /admin, /accounts, /static, /healthz,
# /readyz) to the web tier. This container is the PUBLIC entrypoint for the stack.
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first for layer caching (lockfile present → reproducible).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build against the REAL API by default (mocks off). Override at build time with
# --build-arg if you want a standalone mock build.
ARG VITE_USE_MOCKS=false
ARG VITE_API_BASE_URL=/api
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ── serve ────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
