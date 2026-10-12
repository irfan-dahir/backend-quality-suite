#!/usr/bin/env python3
"""rust adapter: the seam-shaped surface a consumer project actually hits.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/rust_adapter_test.py"

Gives the rust adapter what php/node get from the seam proof and survey test
combined: it loads through the real registry (`for_project`), its capabilities
negotiate against a real Cargo layout, its sweep checks hold positives and
negatives, and its structural extraction (contract headers, error handling,
api consistency) reads a planted fixture the way the audits will.

The whole point of an adapter is that the ENGINE stays language-blind, so
nothing here imports the engine's audits — the adapter is tested through the
seam (`for_project`/`scan_tree`), not around it.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGIN_ROOT = BIN.parent

sys.path.insert(0, str(PLUGIN_ROOT))

from backend_suite.adapters import for_project  # noqa: E402
from backend_suite.engine.scan import scan_tree  # noqa: E402

CARGO = """[package]
name = "fixture"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = "0.7"
serde = { version = "1", features = ["derive"] }
sea-orm = "0.12"
"""

MAIN = """use axum::{Router, routing::get};
use std::env;

/// CONTRACT: the orders surface.
///   total_for(id: string) -> oid
pub struct OrdersAdapter {
    pub service: SeaRepo,
    pub label: String,
}

impl OrdersAdapter {
    pub fn total_for(&self, id: &str) -> u64 {
        let svc = &self.service;
        svc.total_for(id)
    }
    fn private_helper(&self) -> i32 {
        0
    }
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct CreateOrder {
    pub name: String,
}

pub fn app() -> Router {
    Router::new().route("/orders", get(create))
}

async fn create(State(state): State<AppState>) -> impl axum::response::IntoResponse {
    let password = "hunter2long"; // planted secret
    println!("debug {}", password);
    let env_pw = env::var("DB_PASSWORD").expect("set roles");
    match persist(env_pw).await {
        Ok(id) => (axum::http::StatusCode::CREATED, id.to_string()),
        Err(e) => {
            let detail = format!("{e:?}");
            (axum::http::StatusCode::INTERNAL_SERVER_ERROR, detail)
        }
    }
}
"""


def build_root(tmp: str) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "Cargo.toml").write_text(CARGO)
    (repo / "src" / "main.rs").write_text(MAIN)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps({
        "profileVersion": 1,
        "adapters": {"lang": "rust"},
        "source": {"root": "src", "routesFile": "src/main.rs"},
    }))
    return repo


class RustAdapter(unittest.TestCase):
    def test_registry_loads_rust_and_sweeps_positives_and_negatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_root(tmp)
            lang, ctx, checks = for_project(repo)
            self.assertEqual(lang.NAME, "rust")
            findings = scan_tree(repo, repo, checks, globs=lang.FILE_GLOBS)
            by_kind = {f["kind"]: f for f in findings}
            self.assertIn("debug_statement", by_kind)
            self.assertIn("println!", by_kind["debug_statement"]["snippet"])
            self.assertIn("plaintext_secret", by_kind)
            # The negative control: env::var("DB_PASSWORD") is a reference.
            for f in findings:
                self.assertNotIn("DB_PASSWORD", f["snippet"])
            # Rust findings land under src/ only.
            for f in findings:
                self.assertTrue(f["file"].startswith("src/"), f["file"])

    def test_capabilities_negotiate_against_a_cargo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_root(tmp)
            lang, ctx, _ = for_project(repo)
            caps = {c.name for c in lang.capabilities(ctx)}
            self.assertIn("routing", caps)
            self.assertIn("models", caps)          # sea-orm is a dependency
            self.assertIn("axum_routing", caps)    # axum is a dependency
            self.assertNotIn("rocket_routing", caps)
            ev = lang.detect_capability(ctx, "axum_routing")
            self.assertTrue(ev.present)
            self.assertEqual(ev.files, ("src/main.rs",))

    def test_detect_capability_refuses_empty_trees_not_reports_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".backend-suite").mkdir()
            (repo / "src").mkdir()
            (repo / ".backend-suite" / "profile.json").write_text(json.dumps({
                "adapters": {"lang": "rust"},
                "source": {"root": "src"},
            }))
            lang, ctx, _ = for_project(repo)
            with self.assertRaises(Exception) as caught:
                lang.detect_capability(ctx, "routing")
            self.assertIn("no hand-written .rs", str(caught.exception))

    def test_comment_grammar(self):
        from backend_suite.adapters import load
        rust = load("rust")
        src = (
            "// line\n"
            "let u = \"https://x/a\"; // tail\n"
            "let s = r#\"a // b\"#; // real\n"
            "let c = '/'; // one char\n"
            "fn f<'a>(x: &'a str) -> &'a str { x }\n"
            "/* outer /* inner */ done */\n"
            "let g = dbg!(1);\n"
        )
        blanked = rust.blank_comments(src)
        # Comments gone, code intact:
        self.assertNotIn("line", blanked.split("let u")[0])
        self.assertIn("let u = \"https://x/a\";", blanked)
        self.assertIn("let s = r#\"a // b\"#;", blanked)
        self.assertIn("let c = '/';", blanked)
        self.assertIn("fn f<'a>(x: &'a str) -> &'a str { x }", blanked)
        self.assertIn("dbg!", blanked)  # code, not a comment
        # Blanking preserves line count and offsets.
        self.assertEqual(blanked.count("\n"), src.count("\n"))

    def test_contract_banner_and_member_extraction(self):
        from backend_suite.adapters import load
        rust = load("rust")
        banners = rust.block_comments(MAIN)
        self.assertTrue(any("CONTRACT: the orders surface" in text for _, text in banners))
        fields = rust.class_fields(MAIN, "OrdersAdapter")
        self.assertEqual(fields, {"service": 7, "label": 8})
        members = rust.class_members(MAIN, "OrdersAdapter")
        self.assertIn("total_for", members)
        self.assertNotIn("private_helper", members)  # private is not a surface
        # Reads happen through an alias (`let svc = &self.service`), and that
        # is the point of receiver_aliases: the service's members are read,
        # and the audit must see it.
        self.assertEqual(rust.receiver_aliases(MAIN, "service"), {"svc"})
        self.assertEqual(rust.member_reads(MAIN, "svc") & {"total_for"},
                         {"total_for"})

    def test_typed_member_reads_follows_declared_types(self):
        from backend_suite.adapters import load
        rust = load("rust")
        src = (
            "pub struct Holder { pub repo: SeaRepo }\n"
            "pub fn run(repo: SeaRepo) { let _ = repo.total_for(\"x\"); }\n"
        )
        self.assertEqual(rust.typed_member_reads(src, {"SeaRepo"}),
                         {"SeaRepo": {"total_for"}})
        # An untyped receiver resolves through a state-accessor is scoped: it
        # must raise, not report "nothing reads it".
        blind = (
            "pub async fn run(state: AppState) {\n"
            "  let repo = state.get::<SeaRepo>().clone();\n"
            "  repo.total_for(\"x\");\n"
            "}\n"
        )
        with self.assertRaises(Exception) as caught:
            rust.typed_member_reads(blind, {"SeaRepo"})
        self.assertIn("untyped receiver", str(caught.exception))

    def test_error_handling_syntax(self):
        from backend_suite.adapters import load
        rust = load("rust")
        syntax = rust.ERROR_HANDLING
        m = syntax.catch_var.search("Ok(v) => v, Err(e) => handle(e)")
        self.assertEqual(m.group(1), "e")
        m = syntax.catch_var.search(".map_err(|e: AppError| e)")
        self.assertEqual(next(g for g in m.groups() if g), "e")
        self.assertIsNotNone(
            syntax.type_guard("e", "AppError").search("matches!(e, AppError::Io)"))
        self.assertIsNotNone(
            syntax.stringify("e").search("format!(\"{e:?}\")"))
        # e.to_string() is the sanctioned message, not mangling.
        self.assertIsNone(syntax.stringify("e").search("e.to_string()"))

    def test_api_consistency_syntax(self):
        from backend_suite.adapters import load
        rust = load("rust")
        syntax = rust.API_CONSISTENCY
        self.assertEqual(syntax.user_facing.findall(
            'json!({ "message": "Not found" })'), ["Not found"])
        self.assertEqual(syntax.compared.findall('if code == "active"'),
                         [("active", "")])
        self.assertIsNotNone(syntax.tappable.search(
            'Router::new().route("/orders", get(create))'))

    def test_layer_boundaries_refuses_module_imports(self):
        """audit_layer_boundaries must REFUSE on rust, not print a confident
        zero: a `use crate::…` names a module, and a directory-rooted rule
        would otherwise resolve every import as external."""
        from backend_suite.adapters import load
        rust = load("rust")
        self.assertEqual(rust.IMPORT_TARGETS, "module")
        targets = ["crate::config::db", "super::models::User", "axum",
                   "std::collections::HashMap"]
        for target in targets:
            self.assertIsNotNone(
                rust.IMPORT_RE.search(f"use {target};"), target)


if __name__ == "__main__":
    unittest.main(verbosity=2)