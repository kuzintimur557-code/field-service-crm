# Object Storage

## Purpose

Production user files can be stored in Amazon S3 or an S3-compatible provider.
The same backend keeps an off-site mirror of newly created database backups.
Local storage remains the default for development.

Stored object groups:

- task photos at the prefix root;
- client files under `client_files/`;
- call audio under `call_audio/`;
- database backups and PostgreSQL manifests under `backups/`.

## Configuration

```bash
export OBJECT_STORAGE_BACKEND=s3
export S3_BUCKET=field-service-production
export S3_REGION=eu-central-1
export S3_PREFIX=field-service/production
```

`S3_ENDPOINT_URL` enables providers with a custom S3 endpoint.
`S3_ADDRESSING_STYLE` accepts `auto`, `path`, or `virtual` when the provider
requires a specific addressing mode. `S3_LOCAL_CACHE=1` keeps a best-effort
local cache for PDF generation and immediate Telegram photo delivery.

Use the standard AWS credential chain. On AWS, prefer an IAM role. Other
providers can use `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally
`AWS_SESSION_TOKEN`. Credentials, endpoint, bucket name, and object prefix are
not returned by the application's diagnostics APIs.

Optional server-side encryption:

```bash
export S3_SERVER_SIDE_ENCRYPTION=AES256
```

For KMS, use `aws:kms` and set `S3_KMS_KEY_ID`.

The runtime needs these bucket operations:

- `HeadBucket` for readiness;
- `PutObject`, multipart upload operations, `GetObject`, `HeadObject`, and
  `DeleteObject` for application files;
- the same object permissions under `backups/` for the off-site mirror.

The PostgreSQL restore drill still needs the database permissions documented in
`docs/postgresql_migration.md`.

## Existing files

First inspect the migration without network writes:

```bash
python3 scripts/sync_files_to_s3.py --data-dir /path/to/data
```

The JSON report includes only counts and byte totals. When `can_execute` is
`true`, run:

```bash
python3 scripts/sync_files_to_s3.py \
  --data-dir /path/to/data \
  --execute
```

The command uploads every file under `uploads/` and `backups/`, then verifies
each object with `HeadObject`. It never prints the endpoint, bucket, access key,
secret key, or object names.

Keep the local files until the execute report has `"ok": true`, `/ready`
returns `200`, and `/system` shows the S3 backend as available. Existing local
files remain readable during migration because reads use a local fallback when
an object has not reached S3 yet.

## Failure behavior

New writes require the configured S3 object to succeed before the database is
updated with its filename. A failed write returns a Russian error in the
relevant task, client, or call page. Reads may use the local migration cache,
while `/ready` still reports an unavailable bucket. Backup creation reports a
critical error when the local archive cannot be mirrored to S3.
