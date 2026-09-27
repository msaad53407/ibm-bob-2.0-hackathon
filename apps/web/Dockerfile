# Next.js production image — follows the official with-docker/standalone pattern:
# https://github.com/vercel/next.js/tree/canary/examples/with-docker
# Context: ./apps/web  (docker-compose `web.build.context`)
# Requires `output: "standalone"` in next.config.ts.

# ── deps: install once, cached unless lockfiles change ───────────────────────
FROM node:22-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile

# ── builder: compile the app (NEXT_PUBLIC_* are inlined at build time) ──────
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args mirror docker-compose `web.build.args`. NEXT_PUBLIC_* vars are
# baked into the client bundle by `next build` — runtime `environment:` cannot
# change them. Defaults assume localhost port-forwards (local `compose up`).
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_AGENT_URL=http://localhost:8003
ARG NEXT_PUBLIC_PROXY_URL=http://localhost:8080
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_AGENT_URL=$NEXT_PUBLIC_AGENT_URL \
    NEXT_PUBLIC_PROXY_URL=$NEXT_PUBLIC_PROXY_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable pnpm && pnpm run build

# ── runner: minimal prod image — standalone server + static assets only ──────
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME="0.0.0.0" \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
RUN mkdir .next && chown nextjs:nodejs .next

# Standalone output tracing: only the files the server actually imports.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
