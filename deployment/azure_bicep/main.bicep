@description('Location for all resources.')
param location string = resourceGroup().location

@description('Unique suffix for resource names')
param suffix string = uniqueString(resourceGroup().id)

@description('Azure OpenAI Service Name')
param openAiName string = 'aoai-pitchpulse-${suffix}'

@description('Azure AI Translator Service Name')
param translatorName string = 'trans-pitchpulse-${suffix}'

@description('Azure Event Hubs Namespace Name')
param eventHubNamespaceName string = 'eh-pitchpulse-${suffix}'

// 1. Azure OpenAI Service Account
resource openAi 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: openAiName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'OpenAI'
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

// Deploy GPT-4o Model
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAi
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-05-13'
    }
  }
}

// 2. Azure AI Translator Service
resource translator 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: translatorName
  location: location
  sku: {
    name: 'S1'
  }
  kind: 'TextTranslation'
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

// 3. Azure Event Hubs for real-time telemetry streaming
resource eventHubNamespace 'Microsoft.EventHub/namespaces@2021-11-01' = {
  name: eventHubNamespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2021-11-01' = {
  parent: eventHubNamespace
  name: 'match-events'
  properties: {
    messageRetentionInDays: 1
    partitionCount: 4
  }
}

output openAiEndpoint string = openAi.properties.endpoint
output openAiKey string = openAi.listKeys().key1
output translatorEndpoint string = 'https://api.cognitive.microsofttranslator.com'
output translatorKey string = translator.listKeys().key1
