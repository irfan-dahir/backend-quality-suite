#!/usr/bin/env python3
"""go adapter: the seam-shaped surface a consumer project actually hits.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/go_adapter_test.py"

Gives the go adapter what php/node/rust get from the seam proof and survey test
combined: it loads through the real registry (`for_project`), its capabilities
negotiate against a real Go module layout, its sweep checks hold positives and
negatives, and its structural extraction (contract headers, error handling,
api consistency) reads a planted fixture the way the audits will.

The whole point of an adapter is that the ENGINE stays language-blind, so
nothing here imports the engine's audits — the adapter is tested through the
seam (`for_project`/`scan_tree`), not around it.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
import subprocess  # noqa: F401  (kept for parity with rust_adapter_test.py)

BIN = Path(__file__).resolve().parent
PLUGIN_ROOT = BIN.parent

sys.path.insert(0, str(PLUGIN_ROOT))

from backend_suite.adapters import for_project  # noqa: E402
from backend_suite.engine.scan import scan_tree  # noqa: E402

GOMOD = """module github.com/me/fixture

go 1.22

require (
\tgithub.com/gin-gonic/gin v1.10.0
\tgithub.com/golang-jwt/jwt/v5 v5.2.1
)
"""

MAIN = """package main

import (
\t"fmt"
\t"net/http"

\t"github.com/gin-gonic/gin"
\t"github.com/golang-jwt/jwt/v5"
)

// CONTRACT: the orders surface.
//   total_for(id string) -> oid
type OrderAdapter struct {
\tService *UserService
\tLabel   string
\tMax     int `json:"max"`
}

type Storer interface {
\tTotalFor(id string) (uint64, error)
}

func (r *OrderAdapter) TotalFor(id string) (uint64, error) {
\tsvc := r.Service
\tbase, _ := svc.TotalFor(id)
\treturn base + uint64(r.Max), nil
}

func (r *OrderAdapter) privateHelper() {}

func create(c *gin.Context) {
\t_ = jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{})
\tvar password = "hunter2long" // planted secret
\tfmt.Println("debug", password)
\tclaims := c.GetString("role")
\tif claims == "admin" {
\t\tc.JSON(http.StatusOK, gin.H{"message": "granted"})
\t\treturn
\t}
\tif c.Query("memo") == "" {
\t\tc.JSON(http.StatusBadRequest, gin.H{"error": "memo is required"})
\t\treturn
\t}
\t_ = c
}

func main() {
\tr := gin.Default()
\tr.Use(gin.Logger())
\tr.GET("/orders", create)
\t_ = r.Run(":8080")
}
"""


def build_root(tmp: str) -> Path:
    repo = Path(tmp)
    (repo / ".backend-suite").mkdir(parents=True)
    (repo / "cmd" / "api").mkdir(parents=True)
    (repo / "go.mod").write_text(GOMOD)
    (repo / "cmd" / "api" / "main.go").write_text(MAIN)
    (repo / ".backend-suite" / "profile.json").write_text(json.dumps({
        "profileVersion": 1,
        "adapters": {"lang": "go"},
        "source": {"root": ".", "routesFile": "cmd/api/main.go"},
    }))
    return repo


class GoAdapter(unittest.TestCase):
    def test_registry_loads_go_and_sweeps_positives_and_negatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_root(tmp)
            lang, ctx, checks = for_project(repo)
            self.assertEqual(lang.NAME, "go")
            findings = scan_tree(repo, repo, checks, globs=lang.FILE_GLOBS)
            by_kind = {f["kind"]: f for f in findings}
            self.assertIn("debug_statement", by_kind)
            self.assertIn("fmt.Println", by_kind["debug_statement"]["snippet"])
            self.assertIn("plaintext_secret", by_kind)
            # The negative control: a jwt/gin call is not a debug or a secret.
            for f in findings:
                self.assertNotIn("gin-gonic", f["snippet"])
            # Go findings land under the module root, never under .backend-suite.
            for f in findings:
                self.assertTrue(f["file"].startswith("cmd/"), f["file"])

    def test_capabilities_negotiate_against_a_go_module_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_root(tmp)
            lang, ctx, _ = for_project(repo)
            caps = {c.name for c in lang.capabilities(ctx)}
            self.assertIn("routing", caps)
            self.assertIn("gin_routing", caps)    # gin is a require
            self.assertNotIn("echo_routing", caps)
            ev = lang.detect_capability(ctx, "gin_routing")
            self.assertTrue(ev.present)
            self.assertEqual(ev.files, ("cmd/api/main.go",))
            ev = lang.detect_capability(ctx, "routing")
            self.assertTrue(ev.present)
            # A jwt import satisfies policies, and no json DTO means
            # api_resources is not invented either way.
            self.assertTrue(lang.detect_capability(ctx, "policies").present)

    def test_detect_capability_refuses_empty_trees_not_reports_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".backend-suite").mkdir()
            (repo / "cmd").mkdir()
            (repo / ".backend-suite" / "profile.json").write_text(json.dumps({
                "adapters": {"lang": "go"},
                "source": {"root": "."},
            }))
            lang, ctx, _ = for_project(repo)
            with self.assertRaises(Exception) as caught:
                lang.detect_capability(ctx, "routing")
            self.assertIn("no hand-written .go", str(caught.exception))

    def test_comment_grammar(self):
        from backend_suite.adapters import load
        go = load("go")
        src = (
            "// line\n"
            "u := \"https://x/a\" // tail\n"
            "s := `a // b\n` + \"ok\" // real\n"
            "c := '\\\\''\n"
            "/* multi\n done */\n"
            "g := fmt.Println(1)\n"
        )
        blanked = go.blank_comments(src)
        # Comments gone, code intact:
        self.assertNotIn("line", blanked.split("u :=")[0])
        self.assertIn("u := \"https://x/a\"", blanked)
        self.assertIn("`a // b", blanked)  # backtick raw string keeps its content
        self.assertIn("fmt.Println", blanked)  # code, not a comment
        self.assertIn("c := '", blanked)  # the rune literal survives
        self.assertNotIn("done", blanked)  # the block comment is gone
        # Go block comments do NOT nest: the first `*/` closes the comment,
        # exactly opposite to Rust's nesting rule.
        self.assertIn("+ 2", go.blank_comments("x := 1 /* a /* b */ + 2\n"))
        # Blanking preserves line count and offsets.
        self.assertEqual(blanked.count("\n"), src.count("\n"))

    def test_contract_banner_and_member_extraction(self):
        from backend_suite.adapters import load
        go = load("go")
        banners = go.block_comments(MAIN)
        self.assertTrue(any("CONTRACT: the orders surface" in text for _, text in banners))
        fields = go.class_fields(MAIN, "OrderAdapter")
        self.assertEqual(fields, {"Service": 14, "Label": 15, "Max": 16})
        members = go.class_members(MAIN, "OrderAdapter")
        self.assertIn("TotalFor", members)
        self.assertNotIn("privateHelper", members)  # private is not a surface
        # Interface declarations are the surface of an interface too.
        self.assertIn("TotalFor", go.class_members(MAIN, "Storer"))
        # Reads happen through an alias (`svc := r.Service`), and that
        # is the point of receiver_aliases: the service's members are read,
        # and the audit must see it.
        self.assertEqual(go.receiver_aliases(MAIN, "Service"), {"svc"})
        self.assertEqual(go.member_reads(MAIN, "svc") & {"TotalFor"}, {"TotalFor"})

    def test_typed_member_reads_follows_declared_types(self):
        from backend_suite.adapters import load
        go = load("go")
        src = (
            "func run(repo *SeaRepo) { _ = repo.TotalFor(\"x\") }\n"
            "type D struct { repo SeaRepo }\n"
        )
        self.assertEqual(go.typed_member_reads(src, {"SeaRepo"}),
                         {"SeaRepo": {"TotalFor"}})
        # An untyped receiver out of a container accessor is scoped: it
        # must raise, not report "nothing reads it".
        blind = (
            "func run(c *gin.Context) {\n"
            "  svc := c.MustGet(\"sea-repo\")\n"
            "  svc.TotalFor(\"x\")\n"
            "}\n"
        )
        with self.assertRaises(Exception) as caught:
            go.typed_member_reads(blind, {"SeaRepo"})
        self.assertIn("untyped receiver", str(caught.exception))

    def test_error_handling_syntax(self):
        from backend_suite.adapters import load
        go = load("go")
        syntax = go.ERROR_HANDLING
        m = syntax.catch_var.search("if err != nil { return }")
        self.assertEqual(next(g for g in m.groups() if g), "err")
        m = syntax.catch_var.search("err := f()")
        self.assertEqual(next(g for g in m.groups() if g), "err")
        # The init-test form binds the error on the same line as the test.
        m = syntax.catch_var.search("if _, err := f(); err != nil { return }")
        self.assertEqual(next(g for g in m.groups() if g), "err")
        self.assertIsNotNone(
            syntax.type_guard("err", "NotFoundError").search(
                "var nf *NotFoundError\nif errors.As(err, &nf) { }"))
        # %+v flattens the whole struct-wrapped error; %w is the sanctioned wrap.
        self.assertIsNotNone(
            syntax.stringify("err").search('fmt.Sprintf("oops: %+v", err)'))
        self.assertIsNone(
            syntax.stringify("err").search('fmt.Errorf("oops: %w", err)'))
        self.assertIsNotNone(
            syntax.type_test("NotFoundError").search("case *NotFoundError:"))

    def test_api_consistency_syntax(self):
        from backend_suite.adapters import load
        go = load("go")
        syntax = go.API_CONSISTENCY
        self.assertEqual(syntax.user_facing.findall(
            'gin.H{"message": "Not found"}'), ["Not found"])
        self.assertEqual(syntax.compared.findall('if claims == "admin"'),
                         [("admin", "")])
        self.assertIsNotNone(syntax.defaulted.search(
            'if memo == "" { memo = "Default memo" }'))
        self.assertIsNotNone(syntax.tappable.search(
            'r.GET("/orders", create)'))

    def test_layer_boundaries_refuses_module_imports(self):
        """audit_layer_boundaries must REFUSE on go, not print a confident
        zero: a Go `import` names a package path that module-prefixes the
        directory it lives in, and a directory-rooted rule would otherwise
        resolve every same-module import as external."""
        from backend_suite.adapters import load
        go = load("go")
        self.assertEqual(go.IMPORT_TARGETS, "module")
        targets = ['"fmt"',
                   '"github.com/gin-gonic/gin"',
                   'gin "github.com/gin-gonic/gin"',
                   '"myapp/internal/data"']
        for target in targets:
            self.assertIsNotNone(go.IMPORT_RE.search(f"import {target}"), target)


if __name__ == "__main__":
    unittest.main(verbosity=2)