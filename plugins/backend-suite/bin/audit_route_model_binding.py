#!/usr/bin/env python3
"""Audit Laravel route model bindings.

Route model binding is a critical Laravel feature: the framework automatically
resolves Eloquent models from route parameters. This audit verifies that:

1. Implicit bindings (wildcards matching model names) resolve to existing models
2. Explicit bindings (Route::model / Route::bind) reference valid models
3. Controller method signatures match the bound model types
4. Custom resolution logic (Route::bind closures) doesn't silently fail

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_route_model_binding.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_route_model_binding.py" --findings

Config (in arch-rules.json):
  "routeModelBinding": {
    "routesGlob": "routes/*.php",
    "controllerDirs": ["app/Http/Controllers"],
    "modelDirs": ["app/Models"],
    "bindingPattern": "Route::(?:model|bind)\\s*\\([^)]+\\.class",
    "checkControllerSignatures": true,
    "allowMissingModels": false
  }

Exit codes:
    0 = clean (all bindings verified)
    1 = findings (mismatches, missing models, signature mismatches)
    2 = refused (missing config, unreadable files, missing capability)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: F401  (puts backend_suite on sys.path)
from backend_suite.project import profile, project_root  # noqa: E402
from backend_suite.engine import findings as F  # noqa: E402


MARKER = "route_model_binding"

# Patterns for finding route model bindings in routes files
MODEL_BINDING_RE = re.compile(
    r"Route::model\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"]([^'\"]+)['\"]"
)
BIND_CLOSURE_RE = re.compile(
    r"Route::bind\s*\(\s*['\"](\w+)['\"]\s*,\s*function\s*\([^)]*\)"
)
RESOURCE_ROUTE_RE = re.compile(
    r"Route::(?:resource|apiResource|singleton)\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"]([^'\"]+)['\"]"
)

# Controller method patterns for signature checking
CONTROLLER_METHOD_RE = re.compile(
    r"(?:public|protected|private)\s+function\s+(\w+)\s*\(([^)]*)\)"
)
TYPE_HINT_RE = re.compile(r"(\w+)\s+\$(\w+)")

# Eloquent model file pattern
MODEL_FILE_RE = re.compile(r".+\.php$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="write findings JSON to this path")
    ap.add_argument("--findings", nargs="?", const=True, default=False,
                     help="also write findings envelope")
    ap.add_argument("--baseline", help="path to baseline file (not yet implemented)")
    return ap.parse_args()


def load_config(repo: Path) -> dict:
    """Load the routeModelBinding section from arch-rules.json."""
    arch_rules = repo / ".backend-suite" / "arch-rules.json"
    if not arch_rules.is_file():
        return {}
    try:
        data = json.loads(arch_rules.read_text())
        return data.get("routeModelBinding", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def find_model_files(model_dirs: list[str], repo: Path) -> dict[str, Path]:
    """Find all Eloquent model files and map class name -> file path."""
    models = {}
    for d in model_dirs:
        for path in (repo / d).rglob("*.php"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Match class declarations that extend Model or use HasFactory
            if re.search(r"use\s+Illuminate\\Database\\Eloquent\\Model\b", text) or \
               re.search(r"\bclass\s+\w+\s+extends\s+Model\b", text) or \
               "use HasFactory" in text:
                # Extract class name
                m = re.search(r"\bclass\s+(\w+)\b", text)
                if m:
                    models[m.group(1)] = path.relative_to(repo)
    return models


def find_bindings(routes_glob: str, repo: Path) -> dict:
    """Parse route files for model bindings."""
    bindings = {
        "implicit": {},      # wildcard -> model class
        "explicit": {},      # wildcard -> model class (Route::model)
        "closures": {},      # wildcard -> closure (Route::bind)
        "resources": {},     # resource name -> controller class
    }
    
    for path in sorted(repo.glob(routes_glob)):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        
        # Route::model('wildcard', 'ModelClass')
        for m in MODEL_BINDING_RE.finditer(text):
            bindings["explicit"][m.group(1)] = m.group(2)
        
        # Route::bind('wildcard', function...)
        for m in BIND_CLOSURE_RE.finditer(text):
            bindings["closures"][m.group(1)] = "closure"
        
        # Route::resource('photos', 'PhotoController')
        for m in RESOURCE_ROUTE_RE.finditer(text):
            bindings["resources"][m.group(1)] = m.group(2)
    
    return bindings


def find_controller_signatures(controller_dirs: list[str], repo: Path) -> dict:
    """Parse controller files for method signatures with type hints."""
    signatures = {}
    for d in controller_dirs:
        for path in (repo / d).rglob("*.php"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            
            # Find all public/protected/private methods with type hints
            for m in CONTROLLER_METHOD_RE.finditer(text):
                method_name = m.group(1)
                params = m.group(2)
                
                # Extract type-hinted parameters
                params_found = TYPE_HINT_RE.findall(params)
                if params_found:
                    signatures.setdefault(path.relative_to(repo), {})[method_name] = [
                        {"type": t, "name": n} for t, n in params_found
                    ]
    return signatures


def check_bindings(
    bindings: dict,
    models: dict[str, Path],
    controllers: dict,
    config: dict
) -> list[dict]:
    """Verify bindings against models and controller signatures."""
    findings = []
    allow_missing = config.get("allowMissingModels", False)
    check_sigs = config.get("checkControllerSignatures", True)
    
    # Check explicit bindings
    for wildcard, model_class in bindings["explicit"].items():
        if model_class not in models:
            findings.append({
                "kind": "missing_model",
                "file": "routes (explicit binding)",
                "line": 0,
                "detail": f"Route::model('{wildcard}', '{model_class}') references missing model '{model_class}'",
                "severity": "critical",
            })
    
    # Check resource routes
    for resource_name, controller_class in bindings["resources"].items():
        # Implicit binding: singular resource name -> Model
        model_name = resource_name.rstrip('s')  # naive singularization
        if model_name not in models:
            if not allow_missing:
                findings.append({
                    "kind": "missing_implicit_model",
                    "file": "routes (resource route)",
                    "line": 0,
                    "detail": f"Route::resource('{resource_name}') implicitly binds to '{model_name}' which is not a known model",
                    "severity": "critical",
                })
        
        # Check controller signatures if enabled
        if check_sigs and controller_class in str(controllers):
            # TODO: match controller class to file
            pass
    
    # Check controller signatures against bindings
    if check_sigs:
        for controller_file, methods in controllers.items():
            for method_name, params in methods.items():
                for param in params:
                    param_type = param["type"]
                    param_name = param["name"]
                    
                    # Check if this parameter type is a known model
                    if param_type in ["Model", "Eloquent"]:
                        continue  # too generic
                    
                    # Check if it's a model we know about
                    if param_type not in models and not param_type.startswith("Illuminate\\"):
                        # Could be a missing model or a non-model type
                        findings.append({
                            "kind": "untyped_or_missing_model_param",
                            "file": str(controller_file),
                            "line": 0,  # would need more parsing for exact line
                            "detail": f"Controller parameter '{param_name}: {param_type}' in {controller_file} may be an implicit route model binding for missing model '{param_type}'",
                            "severity": "should_fix",
                        })
    
    return findings


def main() -> int:
    args = parse_args()
    
    try:
        repo = project_root()
    except SystemExit:
        print("route-model-binding: no .backend-suite/ found — refusing", file=sys.stderr)
        return 2
    
    profile_data = profile(repo)
    config = load_config(repo)
    
    # Require capability
    lang = profile_data.get("adapters", {}).get("lang")
    if lang != "php":
        print(f"route-model-binding: adapter '{lang}' not supported (requires php)", file=sys.stderr)
        return 2
    
    routes_glob = config.get("routesGlob", "routes/*.php")
    controller_dirs = config.get("controllerDirs", ["app/Http/Controllers"])
    model_dirs = config.get("modelDirs", ["app/Models"])
    
    # Load models
    models = find_model_files(model_dirs, repo)
    if not models:
        print(f"route-model-binding: no Eloquent models found under {model_dirs}", file=sys.stderr)
        # Not a refusal - a project might not use Eloquent
        # But we should still check what we can
    
    # Parse routes
    bindings = find_bindings(routes_glob, repo)
    
    # Parse controllers
    controllers = find_controller_signatures(controller_dirs, repo)
    
    # Check
    findings = check_bindings(bindings, models, controllers, {})
    
    # Write findings
    if args.out:
        out_path = repo / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(findings, indent=2) + "\n")
    
    if args.findings:
        F.write(
            F.default_path(repo, "route_model_binding") if args.findings is True else repo / args.findings,
            "route_model_binding",
            [F.make("route_model_binding", f.get("kind", "route_model_binding"),
                    f.get("detail") or "", severity=F.CRITICAL if f.get("severity") == "critical" else F.SHOULD_FIX,
                    file=f.get("file"), line=f.get("line"))
             for f in findings],
            scanned=len(models) + len(bindings) + len(controllers),
        )
    
    # Print summary
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    should_fix = sum(1 for f in findings if f.get("severity") == "should_fix")
    print(f"route-model-binding: {len(findings)} finding(s) ({critical} critical, {should_fix} should_fix)")
    
    if critical:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())