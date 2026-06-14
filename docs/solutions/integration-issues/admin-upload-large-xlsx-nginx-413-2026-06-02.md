# Admin Upload Large XLSX 413

Date: 2026-06-02

## Symptom

Uploading `docs/企业总表.xlsx` through an nginx-fronted admin-console URL returned
an HTML response:

```text
413 Request Entity Too Large
nginx/1.18.0 (Ubuntu)
```

The workbook is about 3.8 MiB, so this is consistent with an outer nginx using
the default 1 MiB request-body limit.

## Root Cause

The upload request was rejected before it reached FastAPI. Direct requests to the
local admin-console ports accepted the same file:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  curl -F 'file=@docs/企业总表.xlsx' \
  'http://100.64.0.4:5180/api/upload/company?dry_run=true'
```

Therefore the production ingress or preview gateway must set
`client_max_body_size` for the admin-console route. Application-side limits are
still required to avoid unbounded memory use after nginx is fixed.

## Required Invariant

All upload boundaries must agree on the same order of limits:

```text
external nginx client_max_body_size
>= MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES
>= expected XLSX workbook size
```

The application default is 128 MiB. The nginx template is:

```text
apps/admin-console/deploy/nginx/mirothinker-admin-console.conf
```

## Runtime Check

After applying the nginx config, verify:

```bash
nginx -t
nginx -s reload

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  curl -sS -o /tmp/admin-upload.json -w '%{http_code} %{content_type}\n' \
  -F 'file=@docs/企业总表.xlsx' \
  'http://<admin-console-host>/api/upload/company?dry_run=true'
```

Expected result is JSON `200` for a new file, or JSON `409` if the same file is
already being processed. HTML `413` means the outer nginx or platform gateway is
still blocking the request.

## Application Guard

FastAPI now rejects files larger than `MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES` with a
JSON `413` detail containing `code=upload_too_large`. The frontend maps both
nginx HTML 413 and application JSON 413 to a clear large-file upload message.
