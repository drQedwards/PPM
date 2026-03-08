# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:22.12-alpine AS builder

# Copy only the mcp sub-package into /app
COPY mcp /app

WORKDIR /app

# Install all deps (including dev) for the TypeScript build
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Compile TypeScript → dist/
RUN npm run build

# ── Stage 2: Release ─────────────────────────────────────────────────────────
FROM node:22-alpine AS release

COPY --from=builder /app/dist          /app/dist
COPY --from=builder /app/package.json  /app/package.json
COPY --from=builder /app/package-lock.json /app/package-lock.json

ENV NODE_ENV=production

WORKDIR /app

# Production-only install (no devDeps, no lifecycle scripts)
RUN npm ci --ignore-scripts --omit=dev

# Optional: persist KV memory across container restarts
VOLUME ["/app/data"]

ENTRYPOINT ["node", "dist/index.js"]