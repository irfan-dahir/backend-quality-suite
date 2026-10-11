---
name: audit-route-model-binding
description: "Audit Laravel route model bindings — implicit bindings, explicit Route::model/bind, resource routes, and controller signature matching. Use when verifying that route parameters correctly resolve to Eloquent models."
argument-hint: "[--out path] [--findings]"
invocation: auto
maturity: unverified
---

# /audit-route-model-binding

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.

---

Route model binding is a critical Laravel feature: the framework automatically
resolves Eloquent models from route parameters. This audit verifies that:

1. **Implicit bindings** (wildcards matching model names) resolve to existing
   models — e.g. `Route::get('/users/{user}', ...)` expects a `User` model
2. **Explicit bindings** (`Route::model`, `Route::bind`) reference valid models
3. **Resource routes** (`Route::resource`) have their implicit model bindings
   satisfied
4. **Controller method signatures** match the bound model types

---

## Configuration

Add a `routeModelBinding` section to your `.backend-suite/arch-rules.json`:

```json
{
  "routeModelBinding": {
    "routesGlob": "routes/*.php",
    "controllerDirs": ["app/Http/Controllers"],
    "modelDirs": ["app/Models"],
    "checkControllerSignatures": true,
    "allowMissingModels": false
  }
}
```

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `routesGlob` | yes | `routes/*.php` | Glob for route files to scan |
| `controllerDirs` | yes | `["app/Http/Controllers"]` | Directories containing controllers |
| `modelDirs` | yes | `["app/Models"]` | Directories containing Eloquent models |
| `checkControllerSignatures` | no | `true` | Whether to check controller method signatures |
| `allowMissingModels` | no | `false` | Allow resource routes without matching models |

---

## Exit Codes

- **0** — clean (all bindings verified)
- **1** — findings (missing models, signature mismatches)
- **2** — refused (missing config, unreadable files, unsupported adapter)

---

## Example Findings

### Missing explicit model
```json
{
  "kind": "missing_model",
  "file": "routes/api.php",
  "detail": "Route::model('user', 'App\\Models\\User') references missing model 'App\\Models\\User'",
  "severity": "critical"
}
```

### Missing implicit model for resource route
```json
{
  "kind": "missing_implicit_model",
  "file": "routes/api.php",
  "detail": "Route::resource('photos') implicitly binds to 'photo' which is not a known model",
  "severity": "critical"
}
```

### Controller parameter type not found
```json
{
  "kind": "untyped_or_missing_model_param",
  "file": "app/Http/Controllers/PhotoController.php",
  "detail": "Controller parameter 'photo: Photo' in app/Http/Controllers/PhotoController.php may be an implicit route model binding for missing model 'Photo'",
  "severity": "should_fix"
}
```

---

## How It Works

1. **Model Discovery** — scans `modelDirs` for classes extending `Model`, using `HasFactory`, or `Illuminate\Database\Eloquent\Model`

2. **Binding Extraction** — parses route files for:
   - `Route::model('wildcard', 'ModelClass')` (explicit)
   - `Route::bind('wildcard', fn...)` (closure binding)
   - `Route::resource('name', 'Controller')` (resource routes)

3. **Controller Inspection** — parses controller methods for type-hinted parameters

4. **Verification** — cross-references all bindings against discovered models

---

## Common Issues

| Issue | Fix |
|-------|-----|
| `Route::model('user', 'App\\Models\\User')` but `User` doesn't exist | Create the model or fix the class path |
| `Route::resource('photos')` but no `Photo` model | Create `Photo` model or use `allowMissingModels: true` |
| Controller has `Photo $photo` param but no `Photo` model | Create model or fix type hint |

---

## Related Skills

- `/audit-route-coverage` — verifies every route has a controller method
- `/audit-contract-headers` — verifies controller contracts match service interfaces
- `/audit-api-consistency` — checks API response consistency