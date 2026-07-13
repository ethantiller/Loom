.PHONY: start-app start-frontend

start-frontend:
	cd frontend && npm run dev

start-db:
	cd app && make db-up

stop-db:
	cd app && make db-down

start-api:
	cd app && make dev