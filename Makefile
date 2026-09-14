.PHONY: up down logs seed scenario test lint \
	tf-fmt tf-validate tf-plan-demo tf-plan-reference destroy

COMPOSE := docker compose -f deploy/docker-compose.yml
TF := terraform -chdir=deploy/terraform

up:
	$(COMPOSE) up --build -d postgres recorder mediator demo investigator

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

seed:
	$(COMPOSE) run --rm seed
	$(COMPOSE) run --rm seed-baseline

# make scenario SCENARIO=ticket_injection_exfil
scenario:
	$(COMPOSE) run --rm agent-runner \
		python -m scenarios.agent.run_scenario --scenario-id "$(SCENARIO)"

test:
	. .venv/bin/activate && python -m pytest -q

# -- AWS (M11) ----------------------------------------------------------
# validate/fmt only — plan and apply are run by whoever actually holds AWS
# credentials, never automatically from here. See deploy/terraform/envs/
# for the demo vs. reference cost breakdowns before ever running plan.

tf-fmt:
	$(TF) fmt -recursive

tf-validate:
	$(TF) init -backend=false
	$(TF) validate

tf-plan-demo:
	$(TF) plan -var-file=envs/demo.tfvars

tf-plan-reference:
	$(TF) plan -var-file=envs/reference.tfvars

# make tf-ecr-push PROFILE=demo ACCOUNT_ID=123456789012 REGION=us-east-1
tf-ecr-push:
	./deploy/terraform/ecr_push.sh "$(PROFILE)" "$(ACCOUNT_ID)" "$(REGION)"

# Tears down a deployed demo stack cleanly, no orphaned resources. Reads
# the same tfvars the deploy used — pass PROFILE=reference to destroy that
# one instead (only meaningful if it was ever actually applied).
PROFILE ?= demo
destroy:
	$(TF) destroy -var-file=envs/$(PROFILE).tfvars
