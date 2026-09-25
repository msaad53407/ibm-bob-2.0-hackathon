# Root-context image: resolves the @guardrail/contracts workspace dep with pnpm.
# Build from the repo root:  docker build -f services/proxy/Dockerfile .
FROM node:22-alpine
RUN corepack enable && corepack prepare pnpm@11.15.1 --activate
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY services/proxy/package.json ./services/proxy/package.json
COPY packages/contracts ./packages/contracts
RUN pnpm install --frozen-lockfile --filter @guardrail/proxy
RUN pnpm --filter @guardrail/contracts build
COPY services/proxy/src ./services/proxy/src
WORKDIR /app/services/proxy
EXPOSE 8080
CMD ["node", "src/index.js"]
