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
   RG=/subscriptions/<subId>/resourceGroups/rg-pitchpulse
   az role assignment create --assignee <appId> --role Contributor --scope $RG
   # May grant only the six roles the template uses, nothing else.
   # The sixth, Monitoring Metrics Publisher (3913510d-...), is only used with
   # DEPLOY_OBSERVABILITY=true (crew tracing).
   ROLES="7f951dda-4ed3-4680-a7ca-43fe172d538d, 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, a97b65f3-24c7-4388-baec-2e87135dc908, 2b629674-e913-4c01-ae53-ef4638d8f975, a638d3c7-ab3a-418d-83e6-5f17a39d4fde, 3913510d-42f4-4e42-8a64-420c390055eb"
   az role assignment create --assignee <appId> \
     --role "Role Based Access Control Administrator" --scope $RG \
     --condition-version 2.0 --condition "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$ROLES})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$ROLES}))"
   ```
   The deploy identity can manage resources in this one resource group and
   hand out only the six roles the app and simulator need. If you already ran
   this with five roles, run the `az role assignment create ... --condition`
   line again with the new `ROLES` (or edit the condition in the portal)
   before setting `DEPLOY_OBSERVABILITY=true`.
3. **GitHub settings**: Settings -> Environments -> new environment
   `production`, add yourself as required reviewer and set deployment
   branches to `main` only. Settings -> Secrets and
   variables -> Actions -> **Variables** (not secrets, none of these are
   secret): `AZURE_CLIENT_ID` (appId), `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`.
4. **Approve the first deploy**: run Actions -> deploy -> `what-if`, review,
   then `deploy` (see `deployment/README.md`).
5. **Approve Azure AI spend**, then set repo variables `DEPLOY_OPENAI=true`
   and `MATCHMIND_AI_ENABLED=true` (and `DEPLOY_TRANSLATOR=true` for
   Translator) and redeploy. Unset means off. Optional, small cost: set
   `DEPLOY_OBSERVABILITY=true` for crew traces in Application Insights and the
   Foundry Tracing page (needs the sixth role above). Optional, paid: run
   Foundry's Groundedness and Relevance evaluators on a sample of the
   evaluation set (`docs/EVALUATION.md`).
6. **GitHub**: turn on secret scanning and push protection
   (Settings -> Code security). Review and merge the engine branch.
7. **Hackathon registration**: make sure both builders are listed as team
   members (prizes are split per member).
8. **Demo video**: record (< 2 min), upload to YouTube or Vimeo as public or
   unlisted, check it plays when logged out.
9. **Submit** by 26 Oct (deadline 27 Oct): project page, pitch, video URL,
   public repo URL. Make the repo public only after the security review passes.
10. **Microsoft Fabric (optional, owner-run)**: start a Fabric trial capacity
    (free for 60 days, paid after), then follow `analytics/fabric/README.md`
    to load the Lakehouse export and the Eventhouse queries. Nothing there is
    connected yet; decide who pays after the trial before keeping it.
