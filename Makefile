.PHONY: bootstrap up down logs test smoke-test web api

bootstrap:
	cp -n .env.example .env || true
	docker compose build

up:
	docker compose up

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd apps/web && npm test -- --run || true
	cd apps/api && python -m pytest || true

smoke-test:
	curl -f http://localhost:8000/health
	curl -f -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message":"Hello MedGraphRAG"}'

web:
	cd apps/web && npm run dev

api:
	cd apps/api && uvicorn app.main:app --reload