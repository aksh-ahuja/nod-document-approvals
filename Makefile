.PHONY: setup api web test test-postgres test-e2e seed azure-email format format-check worker
setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements-dev.txt
	npm --prefix frontend ci
	@test -f .env || cp .env.example .env
	bash scripts/backend.sh migrate

api:
	bash scripts/backend.sh runserver 127.0.0.1:8000

worker:
	bash scripts/backend.sh process_uploads

web:
	npm --prefix frontend run dev

seed:
	bash scripts/backend.sh seed_demo

test:
	bash scripts/test.sh

format:
	.venv/bin/python -m black backend scripts

format-check:
	.venv/bin/python -m black --check backend scripts

test-postgres:
	docker compose up -d db
	docker compose run --rm api python manage.py test tests --verbosity 1
	npm --prefix frontend test
	npm --prefix frontend run build

test-e2e:
	cd frontend && npx playwright install chromium && npm run test:e2e

azure-email:
	.venv/bin/pip install 'azure-communication-email>=1.0,<2' 'azure-identity>=1.19,<2'
	.venv/bin/python scripts/configure_azure_email.py
