# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

bash:
	docker compose run --rm web bash

runserver:
	docker compose up web

build:
	docker compose build

celery-worker:
	docker-compose run --rm web celery -A maker.celery worker -Q default -l INFO

celery-beat:
	docker-compose run --rm web celery -A maker.celery beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

makemigrations:
	docker compose run --rm web django-admin makemigrations

migrate:
	docker compose run --rm web django-admin migrate

format:
	black . && isort . && flake8 . && reuse lint

pytest:
	docker-compose run --rm web pytest ${ARGS}

shell:
	docker compose run --rm web django-admin shell_plus

notebook:
	docker-compose run --rm web django-admin shell_plus --notebook
