# syntax=docker/dockerfile:1
# Multi-stage: build the Vite SPA, then serve it via nginx which also reverse-
# proxies the Django-served paths (/api, /admin, /accounts, /static, /healthz,
# /readyz) to the web tier. This container is the PUBLIC entrypoint for the stack.
#
# BUILD CONTEXT IS THE REPO ROOT (see docker-compose: context: ., dockerfile:
# frontend/Dockerfile). The SPA imports the platform-agnostic layer at the repo-root
# shared/ dir via the @shared alias (-> ../shared/src, see frontend/vite.config.ts +
# tsconfig). That sibling dir must be present at build time; with the old ./frontend
# context it was never copied, so the @shared re-export shims resolved to nothing and
# `tsc --noEmit` failed — silently breaking every frontend rebuild after the 8.1
# shared-layer extraction (the served bundle went stale). Building from the root with
# shared/ as a sibling of frontend/ reproduces the local layout exactly.
FROM node:20-alpine AS build
WORKDIR /app/frontend

# Install deps first for layer caching (lockfile present -> reproducible). shared/
# has no deps of its own (its peer axios resolves from frontend/node_modules via the
# vite alias), so only the frontend lockfile is installed.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# The shared layer must sit as a SIBLING of frontend so `../shared/src` resolves
# (matches the @shared alias + tsconfig path). Copy it before the app sources.
COPY shared /app/shared
COPY frontend ./

# Build against the REAL API by default (mocks off). Override at build time with
# --build-arg if you want a standalone mock build.
ARG VITE_USE_MOCKS=false
ARG VITE_API_BASE_URL=/api
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ── serve ────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
