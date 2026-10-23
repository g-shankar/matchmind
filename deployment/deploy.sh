#!/usr/bin/env bash
# One-command deploy of PitchPulse to Azure.
#
# Runs from Azure Cloud Shell (Bash) or any machine with the Azure CLI signed
# in (`az login`). No Docker needed: the image is built inside the container
# registry with `az acr build`. It does what .github/workflows/deploy.yml
# does, for owners who have not set up the GitHub sign-in yet.
#
#   deployment/deploy.sh            preview only (what-if); creates nothing, costs nothing
#   deployment/deploy.sh --apply    create or update everything and print the preview URL
#
# Settings (environment variables, all optional; unset means off):
#   RESOURCE_GROUP               default rg-pitchpulse
#   LOCATION                     default swedencentral (has gpt-4o-mini quota)
#   MATCHMIND_AI_ENABLED=true    the one switch for the live AI crew (paid, owner
#                                approval first). It also deploys the model unless
#                                DEPLOY_OPENAI=false is set. --apply then asks you
#                                to type yes (or set CONFIRM_PAID_AI=yes).
#   DEPLOY_TRANSLATOR, DEPLOY_OBSERVABILITY, MATCHMIND_LLM_PROVIDER,
#   MATCHMIND_ORCHESTRATOR, MATCHMIND_EVENTHUBS_SOURCE   as in deployment/README.md
#
# Every Azure call signs in with Microsoft Entra ID; no key is read or printed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/deployment/azure_bicep/main.bicep"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-pitchpulse}"
LOCATION="${LOCATION:-swedencentral}"
IMAGE_REPO=pitchpulse

case "${1:-}" in
  "") MODE=what-if ;;
  --apply) MODE=deploy ;;
  -h | --help) sed -n '2,21p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (no option previews, --apply deploys)" >&2; exit 2 ;;
esac

flag() { # true or false, from true/1/yes in any case
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    true | 1 | yes) echo true ;;
    *) echo false ;;
  esac
}

AI_ENABLED="$(flag "${MATCHMIND_AI_ENABLED:-}")"
DEPLOY_OPENAI="$(flag "${DEPLOY_OPENAI:-$AI_ENABLED}")"
PARAMS=(
  "deployOpenAi=$DEPLOY_OPENAI"
  "deployTranslator=$(flag "${DEPLOY_TRANSLATOR:-}")"
  "aiEnabled=$AI_ENABLED"
  "deployObservability=$(flag "${DEPLOY_OBSERVABILITY:-}")"
  "llmProvider=${MATCHMIND_LLM_PROVIDER:-azure_openai}"
  "orchestrator=${MATCHMIND_ORCHESTRATOR:-in_process}"
  "eventHubsSource=$(flag "${MATCHMIND_EVENTHUBS_SOURCE:-}")"
)

az account show --query "{subscription:name, user:user.name}" --output table >/dev/null \
  || { echo "Sign in first: az login" >&2; exit 1; }

echo "Resource group: $RESOURCE_GROUP ($LOCATION)"
echo "Live AI crew:   $AI_ENABLED (model deployed: $DEPLOY_OPENAI)"

if [ "$MODE" = what-if ]; then
  if [ "$(az group exists --name "$RESOURCE_GROUP")" = "false" ]; then
    echo "Resource group $RESOURCE_GROUP does not exist yet: every resource below would be created."
    az bicep build --file "$TEMPLATE" --stdout | python3 -c \
      'import collections, json, sys; [print(f"{n:4} {t}") for t, n in sorted(collections.Counter(r["type"] for r in json.load(sys.stdin)["resources"]).items())]'
  else
    az deployment group what-if --resource-group "$RESOURCE_GROUP" --template-file "$TEMPLATE" \
      --parameters deployApps=false "${PARAMS[@]}"
  fi
  echo
  echo "Preview only; nothing was created. Run again with --apply to deploy."
  exit 0
fi

if [ "$DEPLOY_OPENAI" = true ] || [ "$AI_ENABLED" = true ]; then
  # Paid AI needs the owner's approval: never deploy it from a leftover setting.
  echo "This deploy turns on paid Azure AI (billed per token)."
  if [ "${CONFIRM_PAID_AI:-}" != yes ]; then
    read -r -p "Type yes to continue: " answer || answer=""
    [ "$answer" = yes ] || { echo "Stopped; nothing was created." >&2; exit 1; }
  fi
fi

stamp="$(date -u +%Y%m%d%H%M%S)"
tag="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "$stamp")"

echo "1/3 Base infrastructure"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
registry="$(az deployment group create --resource-group "$RESOURCE_GROUP" --name "base-$stamp" \
  --template-file "$TEMPLATE" --parameters deployApps=false "${PARAMS[@]}" \
  --query properties.outputs.registryName.value --output tsv)"

echo "2/3 Image $IMAGE_REPO:$tag, built in $registry"
az acr build --registry "$registry" --image "$IMAGE_REPO:$tag" \
  --file "$ROOT/deployment/Dockerfile" "$ROOT" --output none
login_server="$(az acr show --name "$registry" --query loginServer --output tsv)"

echo "3/3 App and simulator job"
url="$(az deployment group create --resource-group "$RESOURCE_GROUP" --name "apps-$stamp" \
  --template-file "$TEMPLATE" \
  --parameters deployApps=true containerImage="$login_server/$IMAGE_REPO:$tag" "${PARAMS[@]}" \
  --query properties.outputs.appUrl.value --output tsv)"

ok=false
for _ in $(seq 1 60); do
  if curl -fsS "$url/api/health" >/dev/null 2>&1; then ok=true; break; fi
  sleep 5
done
if [ "$ok" = true ]; then
  echo "Preview: $url"
else
  echo "Deployed, but $url/api/health did not answer within 5 minutes." >&2
  echo "Logs: az containerapp logs show -g $RESOURCE_GROUP -n ca-pitchpulse --tail 50" >&2
  exit 1
fi
echo "Start the live feed: az containerapp job start -g $RESOURCE_GROUP -n caj-pitchpulse-sim"
