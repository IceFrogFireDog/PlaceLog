# syntax=docker/dockerfile:1
# 지구본 사진 프론트엔드 (Next.js standalone). 빌드: docker build -t photo-globe-frontend .
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# rewrites 대상과 NEXT_PUBLIC_* 값은 빌드할 때 고정된다
ARG API_ORIGIN=http://backend:8000
ARG NEXT_PUBLIC_MAP_TILE_URL=""
ARG NEXT_PUBLIC_MAP_ATTRIBUTION=""
ARG NEXT_PUBLIC_PRIVACY_OFFICER=""
ARG NEXT_PUBLIC_PRIVACY_EMAIL=""
ARG NEXT_PUBLIC_PRIVACY_PROCESSORS=""
ARG NEXT_PUBLIC_PRIVACY_EFFECTIVE_DATE=""
ENV API_ORIGIN=$API_ORIGIN \
    NEXT_PUBLIC_MAP_TILE_URL=$NEXT_PUBLIC_MAP_TILE_URL \
    NEXT_PUBLIC_MAP_ATTRIBUTION=$NEXT_PUBLIC_MAP_ATTRIBUTION \
    NEXT_PUBLIC_PRIVACY_OFFICER=$NEXT_PUBLIC_PRIVACY_OFFICER \
    NEXT_PUBLIC_PRIVACY_EMAIL=$NEXT_PUBLIC_PRIVACY_EMAIL \
    NEXT_PUBLIC_PRIVACY_PROCESSORS=$NEXT_PUBLIC_PRIVACY_PROCESSORS \
    NEXT_PUBLIC_PRIVACY_EFFECTIVE_DATE=$NEXT_PUBLIC_PRIVACY_EFFECTIVE_DATE \
    NEXT_OUTPUT=standalone
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:3000/privacy"]
CMD ["node", "server.js"]
