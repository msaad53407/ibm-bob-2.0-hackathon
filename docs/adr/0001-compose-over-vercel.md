# Docker Compose over Vercel for demo infra

Compose runs Stable, Canary, Proxy, and Traffic-runner in one `docker compose up` with no external network need. Decided against Vercel because no trustworthy programmatic traffic-flip hook exists for a live rollback demo.
