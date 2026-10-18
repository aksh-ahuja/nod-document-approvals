param location string = resourceGroup().location
param environmentId string
param appName string = 'nod'
param registryServer string
param managedIdentityId string
param managedIdentityClientId string
param apiImage string
param webImage string
param databaseHost string
param databaseName string = 'nod'
param databaseUser string
param allowedHosts string
param csrfTrustedOrigins string
param emailSender string
param azureEmailEndpoint string
param azureStorageAccount string
param azureStorageContainer string = 'nod-documents'

@secure()
param databasePassword string
@secure()
param secretKey string

resource nod 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        { server: registryServer, identity: managedIdentityId }
      ]
      secrets: [
        { name: 'nod-db-password', value: databasePassword }
        { name: 'nod-secret-key', value: secretKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'nod-web'
          image: webImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'NOD_API_UPSTREAM', value: '127.0.0.1:8000' }
            { name: 'NOD_INGRESS_MODE', value: 'azure' }
          ]
          probes: [
            { type: 'Readiness', httpGet: { path: '/', port: 8080 }, initialDelaySeconds: 5, periodSeconds: 10 }
          ]
        }
        {
          name: 'nod-api'
          image: apiImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'NOD_DEBUG', value: 'false' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'NOD_SECRET_KEY', secretRef: 'nod-secret-key' }
            { name: 'NOD_ALLOWED_HOSTS', value: '${allowedHosts},localhost,127.0.0.1' }
            { name: 'NOD_CSRF_TRUSTED_ORIGINS', value: csrfTrustedOrigins }
            { name: 'NOD_TRUSTED_PROXY_IPS', value: '127.0.0.1' }
            { name: 'NOD_COOKIE_SECURE', value: 'true' }
            { name: 'NOD_DB_ENGINE', value: 'postgresql' }
            { name: 'NOD_DB_HOST', value: databaseHost }
            { name: 'NOD_DB_NAME', value: databaseName }
            { name: 'NOD_DB_USER', value: databaseUser }
            { name: 'NOD_DB_PASSWORD', secretRef: 'nod-db-password' }
            { name: 'NOD_DB_SSLMODE', value: 'require' }
            { name: 'NOD_EMAIL_PROVIDER', value: 'azure' }
            { name: 'NOD_EMAIL_SENDER', value: emailSender }
            { name: 'NOD_AZURE_EMAIL_ENDPOINT', value: azureEmailEndpoint }
            { name: 'NOD_STORAGE_PROVIDER', value: 'azure' }
            { name: 'NOD_AZURE_STORAGE_ACCOUNT', value: azureStorageAccount }
            { name: 'NOD_AZURE_STORAGE_CONTAINER', value: azureStorageContainer }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/api/health/', port: 8000, httpHeaders: [{ name: 'Host', value: 'localhost' }] }, initialDelaySeconds: 10, periodSeconds: 20 }
            { type: 'Readiness', httpGet: { path: '/api/ready/', port: 8000, httpHeaders: [{ name: 'Host', value: 'localhost' }] }, initialDelaySeconds: 5, periodSeconds: 10 }
          ]
        }
      ]
      scale: {
        minReplicas: 2
        maxReplicas: 5
        rules: [{ name: 'nod-http', http: { metadata: { concurrentRequests: '50' } } }]
      }
    }
  }
}
output url string = 'https://${nod.properties.configuration.ingress.fqdn}'


@minValue(1)
@maxValue(10)
param workerReplicas int = 1

resource uploadWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-upload-worker'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: registryServer, identity: managedIdentityId }]
      secrets: [
        { name: 'nod-db-password', value: databasePassword }
        { name: 'nod-secret-key', value: secretKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'nod-upload-worker'
          image: apiImage
          command: ['python', 'manage.py', 'process_uploads']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'NOD_DEBUG', value: 'false' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'NOD_SECRET_KEY', secretRef: 'nod-secret-key' }
            { name: 'NOD_ALLOWED_HOSTS', value: '${allowedHosts},localhost,127.0.0.1' }
            { name: 'NOD_CSRF_TRUSTED_ORIGINS', value: csrfTrustedOrigins }
            { name: 'NOD_COOKIE_SECURE', value: 'true' }
            { name: 'NOD_DB_ENGINE', value: 'postgresql' }
            { name: 'NOD_DB_HOST', value: databaseHost }
            { name: 'NOD_DB_NAME', value: databaseName }
            { name: 'NOD_DB_USER', value: databaseUser }
            { name: 'NOD_DB_PASSWORD', secretRef: 'nod-db-password' }
            { name: 'NOD_DB_SSLMODE', value: 'require' }
            { name: 'NOD_EMAIL_PROVIDER', value: 'azure' }
            { name: 'NOD_EMAIL_SENDER', value: emailSender }
            { name: 'NOD_AZURE_EMAIL_ENDPOINT', value: azureEmailEndpoint }
            { name: 'NOD_STORAGE_PROVIDER', value: 'azure' }
            { name: 'NOD_AZURE_STORAGE_ACCOUNT', value: azureStorageAccount }
            { name: 'NOD_AZURE_STORAGE_CONTAINER', value: azureStorageContainer }
          ]
        }
      ]
      scale: { minReplicas: workerReplicas, maxReplicas: workerReplicas }
    }
  }
}
