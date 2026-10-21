// PitchPulse on Azure: one resource group, no keys anywhere.
//
// Everything authenticates with Microsoft Entra ID through user-assigned
// managed identities (one for the web app, one for the simulator job, each
// with only the roles it needs): Microsoft Foundry (Azure AI Services),
// Translator, Event Hubs and Application Insights have local (key) auth
// switched off, the registry has its admin user switched off, and this
// template outputs names and endpoints only.
//
// Deploy in two passes (the deploy workflow does this):
//   1. deployApps=false  -> identities, registry, logs, Event Hubs, AI services
//   2. push the image, then deployApps=true with containerImage set

targetScope = 'resourceGroup'

@description('Region for every resource.')
param location string = resourceGroup().location

@description('Short prefix for resource names (lowercase letters and digits).')
@minLength(3)
@maxLength(12)
param namePrefix string = 'pitchpulse'

@description('Create the Container App and the simulator job (needs containerImage).')
param deployApps bool = false

@description('Full image reference, e.g. <registry>.azurecr.io/pitchpulse:<sha>.')
param containerImage string = ''

@description('Create the Microsoft Foundry resource (Azure AI Services) with a project and the model deployment. Paid per token; off until the owner approves AI spend.')
param deployOpenAi bool = false

@description('Create Application Insights for crew tracing (Foundry tracing view). Billed per GB ingested; off by default. The deploy identity must be allowed to grant Monitoring Metrics Publisher (setup/owner-todo.md).')
param deployObservability bool = false

@description('Create Azure AI Translator. Paid per character; off by default.')
param deployTranslator bool = false

@description('Turns the AI crew on. Stays false until the owner approves the spend.')
param aiEnabled bool = false

@description('Model and version for the crew, deployed on the Foundry resource.')
param openAiModelName string = 'gpt-4o-mini'
param openAiModelVersion string = '2024-07-18'

@description('Deployment capacity in thousands of tokens per minute.')
@minValue(1)
param openAiCapacity int = 30

@description('Extra web origins allowed to call the API (comma separated). The app URL is always allowed.')
param extraAllowedOrigins string = ''

var suffix = uniqueString(resourceGroup().id)
var names = {
  appIdentity: 'id-${namePrefix}-app'
  simulatorIdentity: 'id-${namePrefix}-sim'
  logs: 'log-${namePrefix}-${suffix}'
  registry: take('cr${namePrefix}${suffix}', 50)
  eventHubs: 'evh-${namePrefix}-${suffix}'
  foundry: 'aif-${namePrefix}-${suffix}'
  foundryProject: 'proj-${namePrefix}'
  appInsights: 'appi-${namePrefix}-${suffix}'
  translator: 'trl-${namePrefix}-${suffix}'
  environment: 'cae-${namePrefix}'
  app: 'ca-${namePrefix}'
  simulatorJob: 'caj-${namePrefix}-sim'
}
var eventHubName = 'match-events'

// Built-in role definition ids.
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  eventHubsDataSender: '2b629674-e913-4c01-ae53-ef4638d8f975'
  eventHubsDataReceiver: 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

// ---------------------------------------------------------------- identity --

// Web app: pulls images, reads the event stream, calls the AI services.
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.appIdentity
  location: location
}

// Simulator job: pulls images and sends to the event stream, nothing else.
resource simulatorIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.simulatorIdentity
  location: location
}

// -------------------------------------------------------------------- logs --

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logs
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------- registry --

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: names.registry
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource appRegistryPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, appIdentity.id, roles.acrPull)
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource simulatorRegistryPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, simulatorIdentity.id, roles.acrPull)
  properties: {
    principalId: simulatorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// -------------------------------------------------------------- event hubs --

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: names.eventHubs
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 1
  }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
  }
}

resource matchEvents 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: eventHubName
  properties: {
    messageRetentionInDays: 1
    partitionCount: 2
  }
}

resource eventHubsSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: matchEvents
  name: guid(matchEvents.id, simulatorIdentity.id, roles.eventHubsDataSender)
  properties: {
    principalId: simulatorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataSender)
  }
}

resource eventHubsReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: matchEvents
  name: guid(matchEvents.id, appIdentity.id, roles.eventHubsDataReceiver)
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataReceiver)
  }
}

// ------------------------------------------------------- microsoft foundry --
//
// An Azure AI Services account with project management on is a Microsoft
// Foundry resource: it hosts the model deployment and the Foundry project
// (agents, evaluations and tracing in the Foundry portal). The crew calls the
// deployment through the resource's Azure OpenAI endpoint with Entra ID.

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (deployOpenAi) {
  name: names.foundry
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  // Projects need a managed identity on the resource; it is given no roles here.
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: names.foundry
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = if (deployOpenAi) {
  parent: foundry
  name: names.foundryProject
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'PitchPulse studio crew'
    description: 'Spotter, Analyst, Commentator, Fact-checker and Producer: evaluations and traces.'
  }
}

// Deployments live on the Foundry resource and are shared by its projects.
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployOpenAi) {
  parent: foundry
  name: openAiModelName
  sku: {
    name: 'GlobalStandard'
    capacity: openAiCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModelName
      version: openAiModelVersion
    }
  }
}

// Inference only: the app identity cannot manage the resource, its
// deployments or the project.
resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployOpenAi) {
  scope: foundry
  name: guid(resourceId('Microsoft.CognitiveServices/accounts', names.foundry), appIdentity.id, roles.cognitiveServicesOpenAiUser)
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
  }
}

// ------------------------------------------------------------ observability --
//
// Workspace-based Application Insights on the same Log Analytics workspace.
// Local auth is off, so ingestion needs an Entra ID token: the ingestion
// string the app receives identifies the resource but cannot write to it on
// its own. The app identity gets Monitoring Metrics Publisher (write
// telemetry, read nothing).

resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (deployObservability) {
  name: names.appInsights
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: true
    RetentionInDays: 30
  }
}

resource appTelemetryPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployObservability) {
  scope: appInsights
  name: guid(resourceId('Microsoft.Insights/components', names.appInsights), appIdentity.id, roles.monitoringMetricsPublisher)
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
  }
}

// Connects the Foundry project to Application Insights, so the project's
// Tracing page reads the crew's spans. Foundry keeps the ingestion string as
// this connection's credential (the AppInsights connection format); it is
// never output.
resource foundryTracing 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = if (deployOpenAi && deployObservability) {
  parent: foundryProject
  name: 'app-insights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: false
    credentials: {
      key: appInsights!.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// -------------------------------------------------------------- translator --

resource translator 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (deployTranslator) {
  name: names.translator
  location: location
  kind: 'TextTranslation'
  sku: { name: 'S1' }
  properties: {
    // A custom subdomain is required for Entra ID (keyless) auth.
    customSubDomainName: names.translator
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource translatorUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployTranslator) {
  scope: translator
  name: guid(resourceId('Microsoft.CognitiveServices/accounts', names.translator), appIdentity.id, roles.cognitiveServicesUser)
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

// ---------------------------------------------------------- container apps --

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.environment
  location: location
  properties: {
    // Logs go through Azure Monitor diagnostic settings, so no workspace key
    // is handed to the environment.
    appLogsConfiguration: { destination: 'azure-monitor' }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource environmentLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: environment
  name: 'to-log-analytics'
  properties: {
    workspaceId: logs.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

var appFqdn = '${names.app}.${environment.properties.defaultDomain}'
var allowedOrigins = empty(extraAllowedOrigins) ? 'https://${appFqdn}' : 'https://${appFqdn},${extraAllowedOrigins}'

var eventHubEnv = [
  { name: 'EVENTHUB_FULLY_QUALIFIED_NAMESPACE', value: '${eventHubs.name}.servicebus.windows.net' }
  { name: 'EVENTHUB_NAME', value: eventHubName }
]

var foundryOpenAiEndpoint = 'https://${names.foundry}.openai.azure.com/'
var foundryProjectEndpoint = 'https://${names.foundry}.services.ai.azure.com/api/projects/${names.foundryProject}'

// Tracing is on only when Application Insights exists. The exporter signs in
// as the app identity (Entra ID); with local auth off, the ingestion string
// alone cannot write telemetry.
var telemetryEnv = deployObservability
  ? [
      { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights!.properties.ConnectionString }
      { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'Authorization=AAD;ClientId=${appIdentity.properties.clientId}' }
      { name: 'OTEL_SERVICE_NAME', value: 'pitchpulse-crew' }
    ]
  : []

var appEnv = [
  { name: 'AZURE_CLIENT_ID', value: appIdentity.properties.clientId }
  { name: 'MATCHMIND_AI_ENABLED', value: string(aiEnabled) }
  { name: 'AZURE_OPENAI_ENDPOINT', value: deployOpenAi ? foundryOpenAiEndpoint : '' }
  { name: 'AZURE_AI_PROJECT_ENDPOINT', value: deployOpenAi ? foundryProjectEndpoint : '' }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiModelName }
  { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
  { name: 'MATCHMIND_TRANSLATOR_ENABLED', value: string(deployTranslator && aiEnabled) }
  { name: 'AZURE_TRANSLATOR_ENDPOINT', value: deployTranslator ? 'https://${names.translator}.cognitiveservices.azure.com/' : '' }
  { name: 'AZURE_TRANSLATOR_REGION', value: location }
]


// The API, WebSocket and built frontend run as one app. The match session is
// held in memory, so it stays at exactly one replica.
resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: names.app
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentity.id}': {} }
  }
  dependsOn: [appRegistryPull, appTelemetryPublisher]
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: registry.properties.loginServer, identity: appIdentity.id }]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'web'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(appEnv, eventHubEnv, telemetryEnv, [
            { name: 'MATCHMIND_ALLOWED_ORIGINS', value: allowedOrigins }
            { name: 'MATCHMIND_PUBLIC_ORIGIN', value: 'https://${appFqdn}' }
          ])
          probes: [
            // Startup runs the crew over the whole demo match (about 20 s),
            // so allow up to 2 minutes before liveness takes over.
            {
              type: 'Startup'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 5
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// Ingest stage: streams the demo match into Event Hubs on demand
// (`az containerapp job start`). Runs only when started; no idle cost.
resource simulatorJob 'Microsoft.App/jobs@2024-03-01' = if (deployApps) {
  name: names.simulatorJob
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${simulatorIdentity.id}': {} }
  }
  dependsOn: [simulatorRegistryPull, eventHubsSender]
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [{ server: registry.properties.loginServer, identity: simulatorIdentity.id }]
    }
    template: {
      containers: [
        {
          name: 'simulator'
          image: containerImage
          command: ['matchmind-sim']
          args: ['live', '--script', 'demo', '--speed', '60', '--sink', 'eventhub']
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: concat([{ name: 'AZURE_CLIENT_ID', value: simulatorIdentity.properties.clientId }], eventHubEnv)
        }
      ]
    }
  }
}

// ----------------------------------------------------------------- outputs --
// Names and endpoints only. Never keys or connection strings.

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output appIdentityClientId string = appIdentity.properties.clientId
output eventHubsNamespace string = '${eventHubs.name}.servicebus.windows.net'
output eventHubName string = eventHubName
output openAiEndpoint string = deployOpenAi ? foundryOpenAiEndpoint : ''
output foundryName string = deployOpenAi ? names.foundry : ''
output foundryProjectEndpoint string = deployOpenAi ? foundryProjectEndpoint : ''
output appInsightsName string = deployObservability ? names.appInsights : ''
output appName string = names.app
output simulatorJobName string = names.simulatorJob
output appUrl string = deployApps ? 'https://${app!.properties.configuration.ingress.fqdn}' : ''
