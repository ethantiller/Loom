.PHONY: start-app start-frontend

start-frontend:
	cd frontend && npm ci && npm run dev

build-frontend:
	cd frontend && npm ci && npm run build && open "dist/mac-arm64/Electron Next.JS.app"

start-db:
	cd app && make db-up

stop-db:
	cd app && make db-down

start-api:
	cd app && make dev