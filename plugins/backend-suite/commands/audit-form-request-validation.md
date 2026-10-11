---
name: audit-form-request-validation
description: "Audit Laravel FormRequest validation classes — missing rules/authorize methods, malformed rules, duplicate rules, empty rules, custom messages/attributes. Use when validating that FormRequest classes follow best practices."
argument-hint: "[--out path] [--findings]"
invocation: auto
maturity: unverified
---

# /audit-form-request-validation

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.

---

Every FormRequest class is a contract: it declares what the request MUST satisfy
before reaching the controller. This audit verifies those contracts are complete
and well-formed.

---

## What It Checks

| Check | Severity | Description |
|-------|----------|-------------|
| `missing_rules_method` | 🔴 critical | `rules()` method is required but missing |
| `missing_authorize_method` | 🔴 critical | `authorize()` method is required but missing |
| `missing_messages_method` | 🟡 should_fix | `messages()` method missing (custom validation messages) |
| `missing_attributes_method` | 🟡 should_fix | `attributes()` method missing (custom field names in messages) |
| `duplicate_rule` | 🟡 should_fix | Same field has multiple validation rules in `rules()` |
| `empty_rules_array` | 🟡 should_fix | `rules()` method exists but returns empty array |

---

## Configuration

Add a `formRequestValidation` section to `.backend-suite/arch-rules.json`:

```json
{
  "formRequestValidation": {
    "requestDirs": ["app/Http/Requests"],
    "requireRules": true,
    "requireAuthorize": true,
    "requireMessages": false,
    "requireAttributes": false,
    "forbidDuplicateRules": true,
    "forbidEmptyRules": true,
    "customRuleDirs": ["app/Rules"]
  }
}
```

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `requestDirs` | yes | `["app/Http/Requests"]` | Directories containing FormRequest classes |
| `requireRules` | no | `true` | Require `rules()` method |
| `requireAuthorize` | no | `true` | Require `authorize()` method |
| `requireMessages` | no | `false` | Require `messages()` method |
| `requireAttributes` | no | `false` | Require `attributes()` method |
| `forbidDuplicateRules` | no | `true` | Flag duplicate field rules |
| `forbidEmptyRules` | no | `true` | Flag empty `rules()` return |
| `customRuleDirs` | no | `["app/Rules"]` | Directories for custom rule classes |

---

## Exit Codes

- **0** — clean (all FormRequests validated)
- **1** — findings (missing methods, malformed rules, etc.)
- **2** — refused (missing config, unreadable files, unsupported adapter)

---

## Example Findings

### Missing rules() method
```json
{
  "kind": "missing_rules_method",
  "file": "app/Http/Requests/StoreUserRequest.php",
  "detail": "FormRequest 'StoreUserRequest' missing required rules() method",
  "severity": "critical"
}
```

### Duplicate rule for same field
```json
{
  "kind": "duplicate_rule",
  "file": "app/Http/Requests/StoreUserRequest.php",
  "detail": "FormRequest 'StoreUserRequest' has duplicate validation rule for field 'email'",
  "severity": "should_fix"
}
```

### Empty rules array
```json
{
  "kind": "empty_rules_array",
  "file": "app/Http/Requests/StoreUserRequest.php",
  "detail": "FormRequest 'StoreUserRequest' has rules() method but returns empty array",
  "severity": "should_fix"
}
```

---

## How It Works

1. **Discovery** — scans `requestDirs` for classes extending `FormRequest` and importing `Illuminate\Foundation\Http\FormRequest`

2. **Method Extraction** — checks for required methods:
   - `rules(): array`
   - `authorize(): bool`
   - `messages(): array` (optional)
   - `attributes(): array` (optional)
   - `prepareForValidation()` (optional)
   - `passedValidation()` (optional)

3. **Rule Parsing** — extracts the rules array and checks for:
   - Empty array
   - Duplicate field keys
   - Well-formed rule strings

4. **Authorization Check** — verifies `authorize()` method exists

---

## Common Issues

| Issue | Fix |
|-------|-----|
| `rules()` method missing | Add `public function rules(): array { return [...]; }` |
| `authorize()` method missing | Add `public function authorize(): bool { return true; }` |
| Duplicate rule for `email` | Merge into single rule: `'email' => 'required|email|unique:users'` |
| Empty rules array | Add actual validation rules or remove the FormRequest if not needed |

---

## Related Skills

- `/audit-route-model-binding` — verifies route parameters match FormRequest expectations
- `/audit-api-consistency` — checks API response consistency
- `/audit-api-consistency` — checks for hard-coded validation messages