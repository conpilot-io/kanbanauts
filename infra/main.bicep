@description('GitHub App ID')
param appId string

@description('Existing Key Vault name holding github-app-private-key and github-webhook-secret')
param keyVaultName string

@description('Function App name')
param functionAppName string = 'kanbanauts-${uniqueString(resourceGroup().id)}'

@description('Storage account name')
param storageAccountName string = 'kbst${uniqueString(resourceGroup().id)}'

@description('App Service Plan name')
param planName string = 'kanbanauts-plan'

@description('OIDC audience / public base URL for the Function App')
param oidcAudience string = ''

@description('Location')
param location string = resourceGroup().location

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'GITHUB_APP_ID', value: appId }
        { name: 'KEY_VAULT_URL', value: keyVault.properties.vaultUri }
        {
          name: 'KANBANAUTS_URL'
          value: oidcAudience != '' ? oidcAudience : 'https://${functionAppName}.azurewebsites.net/api'
        }
        {
          name: 'KANBANAUTS_OIDC_AUDIENCE'
          value: oidcAudience != '' ? oidcAudience : 'https://${functionAppName}.azurewebsites.net/api'
        }
      ]
    }
  }
}

resource kvAccess 'Microsoft.KeyVault/vaults/accessPolicies@2023-07-01' = {
  parent: keyVault
  name: 'add'
  properties: {
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: functionApp.identity.principalId
        permissions: {
          secrets: ['get', 'list']
        }
      }
    ]
  }
}

output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}/api'
output principalId string = functionApp.identity.principalId
