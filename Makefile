.PHONY: help build run shell clean logs

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build   Build Docker image"
	@echo "  run     Run claude interactively"
	@echo "  shell   Open bash in running container"
	@echo "  clean   Stop and remove containers"
	@echo "  logs    Tail hook logs with jq"

build:
	docker compose build

run:
	docker compose run --rm claude claude

shell:
	docker compose exec claude bash

clean:
	docker compose down -v

logs:
	tail -f hooks/logs/latest.jsonl | jq .
