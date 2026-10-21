# Owner to-do

Things only the owners can do. Everything else the team handles.

1. **Azure subscription and resource group**: pick the subscription, a region
   with `gpt-4o-mini` GlobalStandard quota (e.g. `swedencentral`, `eastus2`)
   and a resource group name (e.g. `rg-pitchpulse`).
2. **Let GitHub deploy without keys (OIDC)**, once:
   ```
   az ad app create --display-name pitchpulse-deploy
   az ad sp create --id <appId>
   az ad app federated-credential create --id <appId> --parameters '{
     "name": "github-production",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:g-shankar/matchmind:environment:production",
     "audiences": ["api://AzureADTokenExchange"]}'
   az group create -n rg-pitchpulse -l <region>
   az role assignment create --assignee <appId> --role Owner \
     --scope /subscriptions/<subId>/resourceGroups/rg-pitchpulse
   ```
   Owner on the resource group (not the subscription) is needed because the
   template creates role assignments for the app's managed identity.
3. **GitHub settings**: Settings -> Environments -> new environment
   `production`, add yourself as required reviewer. Settings -> Secrets and
   variables -> Actions -> **Variables** (not secrets, none of these are
   secret): `AZURE_CLIENT_ID` (appId), `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`.
4. **Approve the first deploy**: run Actions -> deploy -> `what-if`, review,
   then `deploy` (see `deployment/README.md`).
5. **Approve Azure AI spend** before `aiEnabled=true` (Azure OpenAI and
   Translator are paid).
6. **GitHub**: turn on secret scanning and push protection
   (Settings -> Code security). Review and merge the engine branch.
7. **Hackathon registration**: make sure both builders are listed as team
   members (prizes are split per member).
8. **Demo video**: record (< 2 min), upload to YouTube or Vimeo as public or
   unlisted, check it plays when logged out.
9. **Submit** by 26 Oct (deadline 27 Oct): project page, pitch, video URL,
   public repo URL. Make the repo public only after the security review passes.
