.PHONY: up down logs seed scenario test lint

COMPOSE := docker compose -f deploy/docker-compose.yml

up:
	$(COMPOSE) up --build -d postgres recorder mediator

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

seed:
	$(COMPOSE) run --rm seed

# make scenario SCENARIO=ticket_injection_exfil
scenario:
	$(COMPOSE) run --rm agent-runner \
		python -m scenarios.agent.run_scenario --scenario-id "$(SCENARIO)"

test:
	. .venv/bin/activate && python -m pytest -q
