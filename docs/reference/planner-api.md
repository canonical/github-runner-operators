# Planner API reference

The planner exposes an HTTP REST API for managing runner flavors, jobs, and
authentication tokens. All endpoints use JSON for request and response bodies
unless otherwise noted.

The base URL depends on how the planner is deployed. In a typical Juju
deployment, the planner is accessible at the address provided by the planner
integration.

## Authentication

The API uses Bearer token authentication with two tiers:

- **Admin token** — a static token configured at planner startup. Required for
  managing auth tokens and listing all flavors.
- **General token** — a 32-byte token created through the admin API and
  encoded as base64 (raw URL encoding, no padding). Accepted by most
  endpoints alongside the admin token.

Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

Requests with a missing or malformed `Authorization` header receive a
`400 Bad Request` response. Invalid tokens receive `401 Unauthorized` with a
`WWW-Authenticate: Bearer` header.

## Health

### Check health

```
GET /health
```

No authentication required.

**Response** `200 OK`:

```json
{"status": "ok"}
```

## Flavors

Flavors define runner configurations that map GitHub Actions workflow labels to
infrastructure. The platform is currently fixed to `github`.

### List all flavors

```
GET /api/v1/flavors
```

**Auth:** Admin token only.

**Response** `200 OK` — JSON array of flavor objects:

```json
[
  {
    "platform": "github",
    "name": "large",
    "labels": ["self-hosted", "linux", "x64", "large"],
    "priority": 10,
    "is_disabled": false,
    "minimum_pressure": 0
  }
]
```

### Create a flavor

```
POST /api/v1/flavors/{name}
```

**Auth:** Admin or general token.

**Path parameters:**

- `name` — unique name for the flavor.

**Request body:**

```json
{
  "platform": "github",
  "labels": ["self-hosted", "linux", "x64", "large"],
  "priority": 10,
  "is_disabled": false,
  "minimum_pressure": 0
}
```

| Field | Type | Description |
|---|---|---|
| `platform` | string | Runner platform. Use `"github"`. |
| `labels` | string array | Labels that trigger this flavor. |
| `priority` | integer | Priority for flavor selection (higher wins). |
| `is_disabled` | boolean | Whether the flavor is disabled. |
| `minimum_pressure` | integer | Minimum pressure threshold before scaling. |

**Responses:**

- `201 Created` — flavor created.
- `409 Conflict` — a flavor with the same name already exists.

### Get a flavor

```
GET /api/v1/flavors/{name}
```

**Auth:** Admin or general token.

**Path parameters:**

- `name` — flavor name. The reserved name `_` is not allowed and returns
  `400 Bad Request`.

**Response** `200 OK` — a single flavor object:

```json
{
  "platform": "github",
  "name": "large",
  "labels": ["self-hosted", "linux", "x64", "large"],
  "priority": 10,
  "is_disabled": false,
  "minimum_pressure": 0
}
```

**Error responses:**

- `400 Bad Request` — reserved name `_` was used.
- `404 Not Found` — flavor does not exist.

### Update a flavor

```
PATCH /api/v1/flavors/{name}
```

**Auth:** Admin or general token.

Currently only the `is_disabled` field can be updated.

**Path parameters:**

- `name` — flavor name. The reserved name `_` is not allowed.

**Request body:**

```json
{
  "is_disabled": true
}
```

**Responses:**

- `204 No Content` — flavor updated.
- `400 Bad Request` — missing `is_disabled` field or reserved name `_`.
- `404 Not Found` — flavor does not exist.

### Delete a flavor

```
DELETE /api/v1/flavors/{name}
```

**Auth:** Admin or general token.

**Path parameters:**

- `name` — flavor name. The reserved name `_` is not allowed.

**Responses:**

- `200 OK` — flavor deleted.
- `400 Bad Request` — reserved name `_` was used.

### Get flavor pressure

```
GET /api/v1/flavors/{name}/pressure
```

**Auth:** Admin or general token.

Returns the current pressure (pending job count) for one or all flavors.

**Path parameters:**

- `name` — flavor name, or `_` to get pressure for all flavors.

**Query parameters:**

- `stream` — set to `true` to receive a streaming NDJSON response instead of
  a single JSON response.

**Response** `200 OK` (non-streaming) — a JSON object mapping flavor names to
pressure values:

```json
{
  "large": 5,
  "small": 2
}
```

**Error responses:**

- `404 Not Found` — no matching flavors found.

#### Streaming mode

When `stream=true`, the response uses `Content-Type: application/x-ndjson` with
`Connection: keep-alive`. Each line is a complete JSON object with the current
pressure values.

The server sends updates when:

- The pressure value changes.
- A periodic heartbeat fires (to keep the connection alive).

The connection remains open until the client disconnects.

## Auth tokens

Auth token endpoints are admin-protected. Use these to manage the general
tokens that clients use to authenticate with the planner.

### Create an auth token

```
POST /api/v1/auth/token/{name}
```

**Auth:** Admin token only.

**Path parameters:**

- `name` — a human-readable name for the token.

**Response** `201 Created`:

```json
{
  "name": "my-charm",
  "token": "<base64-raw-url-encoded-token>"
}
```

Store the returned `token` value securely. It cannot be retrieved again.

**Error responses:**

- `409 Conflict` — a token with the same name already exists.

### List auth tokens

```
GET /api/v1/auth/token
```

**Auth:** Admin token only.

**Response** `200 OK`:

```json
{
  "names": ["my-charm", "another-charm"]
}
```

Only token names are returned, not the token values.

### Delete an auth token

```
DELETE /api/v1/auth/token/{name}
```

**Auth:** Admin token only.

**Path parameters:**

- `name` — token name to delete.

**Responses:**

- `204 No Content` — token deleted, or token did not exist (idempotent).

## Jobs

Jobs represent GitHub Actions workflow runs that have been queued. The platform
path parameter is currently fixed to `github`.

### List jobs

```
GET /api/v1/jobs/{platform}
```

**Auth:** Admin or general token.

**Path parameters:**

- `platform` — runner platform (use `github`).

**Response** `200 OK` — JSON array of job objects:

```json
[
  {
    "platform": "github",
    "id": "12345",
    "labels": ["self-hosted", "linux", "x64"],
    "created_at": "2025-01-15T10:30:00Z",
    "started_at": "2025-01-15T10:31:00Z",
    "raw": {},
    "assigned_flavor": "large"
  }
]
```

### Get a job

```
GET /api/v1/jobs/{platform}/{id}
```

**Auth:** Admin or general token.

**Path parameters:**

- `platform` — runner platform (use `github`).
- `id` — job identifier.

**Response** `200 OK` — a single job object.

**Error responses:**

- `404 Not Found` — job does not exist.

### Update a job

```
PATCH /api/v1/jobs/{platform}/{id}
```

**Auth:** Admin or general token.

Updates the `started_at` and `completed_at` timestamps on a job. Each field
can only be set once; attempting to overwrite a field that is already set
returns an error.

**Path parameters:**

- `platform` — runner platform (use `github`).
- `id` — job identifier.

**Request body:**

```json
{
  "started_at": "2025-01-15T10:31:00Z",
  "completed_at": "2025-01-15T10:45:00Z"
}
```

Both fields are optional. Include only the fields you want to set.

**Responses:**

- `204 No Content` — job updated.
- `400 Bad Request` — invalid payload, or attempting to set a field that
  already has a value.
- `404 Not Found` — job does not exist.

## Data models

### Flavor

| Field | Type | Description |
|---|---|---|
| `platform` | string | Runner platform (currently `"github"`). |
| `name` | string | Unique flavor identifier. |
| `labels` | string array | GitHub Actions labels that map to this flavor. |
| `priority` | integer | Selection priority (higher value wins). |
| `is_disabled` | boolean | Whether the flavor is disabled. |
| `minimum_pressure` | integer | Minimum pressure before scaling triggers. |

### Job

| Field | Type | Description |
|---|---|---|
| `platform` | string | Runner platform. |
| `id` | string | Job identifier. |
| `labels` | string array | Labels from the workflow run. |
| `created_at` | string (RFC 3339) | When the job was created. |
| `started_at` | string (RFC 3339) or null | When the job started running. |
| `completed_at` | string (RFC 3339) or null | When the job completed. |
| `raw` | object | Raw platform-specific data. |
| `assigned_flavor` | string or null | Flavor assigned to the job. |
