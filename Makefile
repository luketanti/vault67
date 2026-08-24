build:
	docker compose build
up:
	docker compose up
down:
	docker compose down
migrate:
	docker compose exec web python manage.py migrate
migrations:
	docker compose exec web python manage.py makemigrations
test:
	docker compose exec web pytest
lint:
	ruff check .
audit:
	XDG_CACHE_HOME=/tmp pip-audit -r requirements-dev.txt
check-deploy:
	DJANGO_SETTINGS_MODULE=config.settings.production python manage.py check --deploy
security:
	bandit -q -r accounts config core dashboard investments ledger tax -x '*/migrations/*'
	XDG_CACHE_HOME=/tmp pip-audit -r requirements-dev.txt
	DJANGO_SETTINGS_MODULE=config.settings.production python manage.py check --deploy
shell:
	docker compose exec web python manage.py shell
createsuperuser:
	docker compose exec web python manage.py createsuperuser
logs:
	docker compose logs -f
