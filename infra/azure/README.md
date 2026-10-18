# Deploy Nod to Azure

The running deployment is **https://nod.haggle.site**. This document describes the
Azure Container Apps deployment option.

The application uses two images: `nod-api` (Django/Gunicorn) and `nod-web` (Nginx/React). The Bicep template runs them together in one Container App, with Nginx forwarding `/api/` to `127.0.0.1:8000`. This preserves a single browser origin for the application APIs. A separate `nod-upload-worker` Container App runs `python manage.py process_uploads` from the API image. It has no ingress and scales independently using `workerReplicas` (default 1). Keep at least one worker running.

The template sets `NOD_INGRESS_MODE=azure` on Nginx and `NOD_TRUSTED_PROXY_IPS=127.0.0.1` on Django. Nginx takes only the rightmost `X-Forwarded-For` address appended by Container Apps and its overwritten `X-Forwarded-Proto`, then replaces the headers sent to Django. Earlier client-supplied addresses and `X-Real-IP` are discarded. Keep public ingress on the web port only; do not expose the API port or enable Azure mode on a web server reachable without the Container Apps ingress. These rules follow [Microsoft's ingress header contract](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview#http-headers).

Compose uses `direct` mode, ignoring incoming forwarding headers and passing the connection address. Its web container has a fixed address, `172.29.80.10`, on the `172.29.80.0/24` bridge, which is the only peer Django trusts. If that subnet conflicts with a local network, change the subnet, web address, and trusted peer together. Clients sharing a NAT address intentionally share an IP bucket. Native `make api` leaves trusted peers empty by default. Other ingress providers need their own verified forwarding contract before changing this configuration.

## Prerequisites

Provision or select:

- A Container Apps environment with network access to PostgreSQL. Enable zone redundancy when availability requirements justify it.
- An Azure Container Registry and a user-assigned managed identity with permission to pull those images.
- Azure Database for PostgreSQL with a `nod` database. Configure private networking, backups, and HA for the intended production tier.
- A Communication Services resource connected to a verified Email Communication Services domain. Give the managed identity the required email-send permission and identify its client ID.
- An Azure Storage account with a private `nod-documents` container. Disable anonymous access and grant the managed identity Storage Blob Data Contributor at account scope for uploads and user-delegation SAS signing. The signed blob endpoint must be reachable by submitters' and reviewers' browsers. Configure Blob service CORS for the exact frontend origin: methods `PUT`, `GET`, `HEAD`; allowed headers `Content-Type`, `x-ms-blob-type`; expose `ETag`; max age 300 seconds. Do not send Nod cookies or CSRF headers to Blob Storage. CORS is not an authorization boundary; the blob-scoped SAS supplies authorization.
- An intended hostname and its HTTPS origin for Django host and CSRF settings.

The template does not create those backing services or grant their permissions. Review costs, networking, and the template before applying it.

## Build images

From the repository root:

```bash
docker build -f backend/Dockerfile -t <registry>.azurecr.io/nod-api:<commit> .
docker build -f frontend/Dockerfile -t <registry>.azurecr.io/nod-web:<commit> .
docker push <registry>.azurecr.io/nod-api:<commit>
docker push <registry>.azurecr.io/nod-web:<commit>
```

Use immutable commit tags or image digests. Supply Bicep parameters through your deployment pipeline and secret store:

| Parameter | Value |
|---|---|
| `environmentId` | Existing Container Apps environment resource ID |
| `registryServer` | `<registry>.azurecr.io` |
| `managedIdentityId` | User-assigned identity resource ID |
| `managedIdentityClientId` | The same identity's client ID |
| `apiImage`, `webImage` | Full image references |
| `databaseHost`, `databaseName`, `databaseUser` | PostgreSQL connection fields |
| `databasePassword` | Secure pipeline input |
| `secretKey` | Unique random Django secret, at least 50 characters |
| `allowedHosts` | Exact application hostnames, comma-separated |
| `csrfTrustedOrigins` | Exact HTTPS origins, comma-separated |
| `emailSender` | Azure verified sender address |
| `azureEmailEndpoint` | Communication Services endpoint |
| `azureStorageAccount` | Storage account holding private documents and previews |
| `azureStorageContainer` | Private container, default `nod-documents` |
| `workerReplicas` | Upload-validation processes, default 1; tune to queue age and database capacity |

For example, generate a secret locally with `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'` and place it directly into the secret store. Keep the key stable across replicas and deployments because sessions and OTP verification depend on it.

Before promoting a new revision, run `python manage.py migrate --noinput` once using a Container Apps Job or release job with the API image and the same database settings. Migrations intentionally do not run in every production API replica. For an initial release, migrate the empty database before directing traffic to the application.

Deploy the template with your reviewed parameter file or pipeline inputs:

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file infra/azure/nod.bicep \
  --parameters @<private-parameters-file>
```

Do not commit a parameter file containing secrets. The template outputs the application URL. If using the generated Container Apps hostname, include that hostname/origin in the host and CSRF parameters before exposing the application to users.

## Operational checks

- `/api/health/` returns process health; `/api/ready/` queries PostgreSQL.
- Verify cookies have Secure/HttpOnly attributes and login/register reject missing CSRF tokens.
- Send a registration code to an address you control and verify delivery, expiry, resend, and login.
- Verify a newly registered account can submit documents and review only documents assigned to it; never enable demo seeding in production.
- Confirm an unrelated reviewer cannot read a submission.
- Upload and view a PDF, TXT, and DOCX; verify SAS expiry, private-container settings, PDF conversion, and original-file downloads. Never apply a blanket object-expiration rule to active documents or cached previews.
- Verify the browser sends raw file bytes to the storage hostname, while `submissions/create/` contains only `upload_id` and metadata.
- Stop the worker during an upload, confirm the job stays queued, then restart it and verify completion. Test an expired lease and a changed staging ETag. Completion alone must not make the file reviewable.
- Monitor validation queue age, expired leases, rejection/retry rates, cleanup failures, application errors, PostgreSQL connections, storage usage, and backup recovery.
- Configure a lifecycle policy that removes objects under `staging/` after a few days. The worker normally cleans up after 24 hours; the lifecycle rule catches incomplete uploads or writes arriving after cleanup. Never apply that rule to `documents/` or `previews/`. Azure SAS cannot enforce the 10 MB ceiling during transfer; metadata checks, bounded validation, signing quotas, and storage monitoring are required.
- Set edge request/abuse limits. Verify distinct client addresses use independent authentication buckets and client-supplied forwarding headers cannot change their bucket. Preserve the configured trusted proxy chain when changing ingress.
- Schedule `python manage.py clearsessions` and `python manage.py cleanup_auth` daily.

Two replicas are a starting setting, not a measured availability guarantee. The database, email dependency, ingress, and region configuration also determine resilience.

## AWS migration

Reuse the API and web images in an ECS task and point Django at RDS PostgreSQL. Update the Nginx upstream for the task networking configuration. Copy document/preview objects to a private S3 bucket preserving their keys, and set `NOD_STORAGE_PROVIDER=s3`, `NOD_S3_BUCKET`, and `AWS_DEFAULT_REGION`. Use an IAM task role for storage. Run the same upload-worker command as a separate ECS service. Configure S3 bucket CORS for the frontend origin with `PUT`, `GET`, `HEAD`, allowed header `Content-Type`, and exposed header `ETag`. Configure a `staging/` lifecycle policy and test signed PUT uploads, conditional reads, and final-object isolation. Migrate database/session settings and add an SES email provider behind the email factory. Test a planned cutover before changing DNS.

References: [Container Apps template schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2024-03-01/containerapps), [Azure Email quickstart](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/email/send-email), [Azure SAS limitations](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview), [S3 presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).
