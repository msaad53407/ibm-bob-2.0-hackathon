# pnpm plus Turbo monorepo with Compose

pnpm workspaces manage JS (web, proxy, contracts); uv/pip manage Python services; Turbo runs JS tasks only. Docker Compose builds each service from its folder so local dev and demo share the same Dockerfiles.
