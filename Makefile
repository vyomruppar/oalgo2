.PHONY: install backend frontend dev test scan

install:
	cd backend && uv sync
	cd frontend && pnpm install

backend:            ## research API on http://localhost:8000
	cd backend && uv run uvicorn app.api.main:app --port 8000

frontend:           ## dashboard on http://localhost:3000
	cd frontend && pnpm build && pnpm start

dev:                ## both, with hot reload for the dashboard
	(cd backend && uv run uvicorn app.api.main:app --port 8000) & (cd frontend && pnpm dev); wait

test:
	cd backend && uv run pytest
	cd frontend && pnpm typecheck && pnpm test

scan:               ## one full scan from the command line (backend need not be running)
	cd backend && uv run python -c "from app.db import init_db; from app.jobs.pipeline import run_scan; init_db(); print('scan', run_scan())"
