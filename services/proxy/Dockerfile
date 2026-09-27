# Proxy (Node.js/Express) — root-context image so the
# @guardrail/contracts workspace dep resolves.
# Build from the repo root:  docker build -f services/proxy/Dockerfile .
# Multi-stage: full install + tsc build up front, prod-only deps in runner.

# ── deps: workspace install, cached unless lockfiles/package.jsons change ────
FROM node:22-alpine AS deps
RUN corepack enable pnpm
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY services/proxy/package.json ./services/proxy/package.json
COPY packages/contracts/package.json packages/contracts/tsconfig.json ./packages/contracts/
COPY packages/contracts/src ./packages/contracts/src
RUN pnpm install --frozen-lockfile --filter @guardrail/proxy...

# ── builder: compile the contracts workspace dep ─────────────────────────────
FROM node:22-alpine AS builder
RUN corepack enable pnpm
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/services/proxy ./services/proxy
COPY --from=deps /app/packages/contracts ./packages/contracts
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
RUN pnpm --filter @guardrail/contracts build

# ── runner: prod deps only, non-root ──────────────────────────────────────────
FROM node:22-alpine AS runner
ENV NODE_ENV=production \
    PORT=8080
WORKDIR /app

# Prod-only install (devDeps like typescript stay in builder).
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY services/proxy/package.json ./services/proxy/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
RUN corepack enable pnpm \
    && pnpm install --prod --frozen-lockfile --filter @guardrail/proxy... \
    && pnpm store prune

COPY --from=builder /app/packages/contracts/dist ./packages/contracts/dist
COPY services/proxy/src ./services/proxy/src

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 proxyjs \
    && chown -R proxyjs:nodejs /app
USER proxyjs
WORKDIR /app/services/proxy

EXPOSE 8080
CMD ["node", "src/index.js"]
