# ── Stage 1: Build ────────────────────────────────────────────
FROM node:22.12-alpine AS builder

COPY mcp /app
WORKDIR /app

RUN --mount=type=cache,target=/root/.npm npm install
RUN npm run build          # tsc → dist/

# ── Stage 2: Release ──────────────────────────────────────────
FROM node:22-alpine AS release

COPY --from=builder /app/dist            /app/dist
COPY --from=builder /app/package.json    /app/package.json
COPY --from=builder /app/package-lock.json /app/package-lock.json

ENV NODE_ENV=production
WORKDIR /app

RUN npm ci --ignore-scripts --omit=dev

VOLUME ["/app/data"]

ENTRYPOINT ["node", "dist/index.js"]