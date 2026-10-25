# Local checks. `make check` mirrors CI.
.PHONY: check backend frontend bicep image licence-check openapi

check: backend frontend bicep licence-check

backend:
	cd backend && ruff check . && ruff format --check . && pytest -q

frontend:
	cd frontend && npm ci --no-audit --no-fund && npm run build

bicep:
	az bicep build --file deployment/azure_bicep/main.bicep --stdout > /dev/null

image:
	docker build -f deployment/Dockerfile -t pitchpulse:local .

licence-check:
	cd backend && pip install --quiet pip-licenses && pip-licenses --partial-match --fail-on="GPL;AGPL;SSPL;UNKNOWN;NonCommercial;CC-BY-NC;BUSL;Commons Clause"
	cd frontend && npx --yes license-checker --production --excludePrivatePackages --failOn "GPL;AGPL;SSPL;UNKNOWN;UNLICENSED;CC-BY-NC-4.0;BUSL-1.1"

# Regenerate the committed API contract (docs/openapi.json); a backend test fails when it is stale.
openapi:
	cd backend && PYTHONPATH=src python3 -m matchmind.api.openapi_export
