# RFC-0001 — Evidence-backed maturity for all skills, and a promotion pipeline for tooling

| | |
|---|---|
| Status | Accepted (phased, gated on Workstream A1 — see §8) |
| Author(s) | Irfan Dahir (direction), drafted by Claude Code |
| Reviewers | Irfan Dahir |
| Date opened | 2026-09-14 |
| Date decided | 2026-09-14 |
| Supersedes / superseded by | Extends roadmap Workstream A (A1 `verify.py`, A2 evidence-backed maturity) rather than replacing it |

A proposal, not a decision. This document argues for a specific change before
it happens; once a decision is made, the outcome and its reasoning belong in
the decisions log — this document stays as the record of what was proposed
and why, not as a second copy of the decision log.

---

## 1. Summary

Two related extensions to what `docs/ROADMAP.md` already scoped for `verify.py`:

1. **Widen evidence-backed maturity beyond this suite's own components.** As designed, `verify.py`/A2 only proves whether `ai-backend-suite`'s own audits/skills work against a consumer project. This proposal extends the same evidence mechanism to a project's *own* bespoke skills and agents (e.g. a real consumer mobile project's `.claude/commands/cut-release.md`) — one honest maturity system, not two.
2. **A promotion pipeline for tooling, not just components.** This suite already promotes UI *components* from an app into the shared design system (`/promote-component`, backed by `audit_promotion_candidates`/`audit_reinvented_components`). This proposal adds the mirror version one level up: when a project-local skill or agent is genuinely reused, or the same kind of tool is independently reinvented across projects, the LLM proposes promoting it into `ai-backend-suite` itself — the suite grows by absorbing what actually gets used, with a human approving every promotion, never by autonomous merge.

Together these make the suite self-observing (it knows what actually works, not what was asserted) and self-improving (it grows from real usage patterns, not from someone deciding in advance what should exist) — while keeping every consequential decision in a human's hands, per this project's own tier philosophy.

## 2. Motivation

**Problem 1 — maturity is an assertion, and it's scoped too narrowly even where it exists.** `docs/ROADMAP.md`'s Workstream A already identified that `maturity: proven` on this suite's own components is "currently a word someone typed," with `verify.py` proposed as the fix. But a real audit of the three repos this session touched shows the same problem exists one level down, uncovered: a real consumer project (mobile) has its own `cut-release.md`, and nothing anywhere records whether it's actually reliable, when it was last exercised, or against what. A project's own tooling gets zero of the rigor this suite insists on for design tokens, copy, or accessibility. That's an inconsistency — the suite audits everything else in a project except the project's own automation.

**Problem 2 — the suite currently only grows top-down.** Every component in this suite so far was deliberately authored by a person deciding it should exist. Meanwhile, `audit_reinvented_components`/`audit_promotion_candidates` already prove that real projects independently reinvent the same UI patterns — the same is almost certainly true of tooling: two Flutter consumer repos likely have overlapping ad hoc scripts or slash commands solving the same problem slightly differently, invisible to each other. Without a promotion path, that duplication just persists, the same way UI duplication did before `/promote-component` existed.

If neither problem is addressed: maturity claims stay partial and asserted, and the suite's growth stays entirely dependent on a person noticing a pattern by hand — which per this project's own governing principle ("an audit that reports nothing must never look like a clean codebase") is exactly the kind of gap this suite exists to close everywhere else.

## 3. Proposal

### 3a. Extend evidence-backed maturity to project-owned tooling

- A project's `.backend-suite/profile.json` gains an optional pointer (following the same pattern as `componentCapabilities.file`/`componentMaturity.file` from #61/#48) to a manifest of the project's own skills/agents worth tracking — e.g. `.claude/commands/*.md`, `.claude/agents/*.md` — read directly rather than requiring a separate hand-maintained list, mirroring how `component_shape.py` derives component data from source instead of duplicating it.
- `verify.py` (A1, not yet built) is extended to accept either a suite component *or* a project-local skill/agent as its target. The evidence file format (sketched in A2, `.backend-suite/evidence/<name>.json`) is identical either way — the mechanism doesn't care whether the thing being verified ships with `ai-backend-suite` or was authored by the project.
- Verifying a project-local skill is necessarily narrower than verifying an audit script: most skills are prose instructions for an LLM to follow, not deterministic code. The honest slice: did it run, did it exit cleanly (for skills backed by a script), has it been exercised recently, does its own documented contract still match what it does. This is the same "verified / refused / failed, never a boolean" discipline A1 already commits to for suite components — extended, not loosened.

### 3b. A promotion pipeline for tooling

Two distinct triggers, both ending the same way — a **proposal**, never an autonomous merge. They split cleanly along a hard constraint, scoped in **RFC-0001 §8**: Claude Code's plugin hook system only fires on tool-call events (`Write`/`Edit`/`Bash` — see `hooks/audit_on_edit.py`'s own `PostToolUse` matcher), never on skill/command invocation itself. So per-project *invocation frequency* is not mechanically observable for a prose skill, and the two triggers apply to different kinds of tooling:

- **Reuse signal (script-backed tools only):** a project-local tool that's backed by an actual script (not just prose) gets its usage signal for free, once §3a's evidence mechanism exists — every evidence-file write already carries a timestamp and a target, so evidence-file frequency *is* the reuse signal, no separate tracking infrastructure needed.
- **Convergence signal (the only trigger for prose skills):** the same *kind* of tool exists independently in two or more consumer projects — detected the same way `audit_reinvented_components`/`audit_promotion_candidates` already detect UI duplication (structural similarity, not just naming), but pointed at `.claude/commands/`/`.claude/agents/` instead of Dart widgets. Since most project-local skills are prose Claude follows in conversation with no execution trace at all, convergence — not usage frequency — has to be the real trigger for the harder, more common case. A voluntary self-logging convention (a skill appends to a local `.backend-suite/usage.log`, the same way `log-decision` appends to a decision log) remains available as a labeled *soft* signal a promotion proposal can cite alongside convergence, but it's opt-in and unenforced, never treated as a true frequency count.

When either fires, the LLM drafts a promotion proposal — following the same pattern `capture-backlog`/`log-decision` already use: **draft only, never commit**. The draft states: what the tool does, where it's currently used, the evidence (from §3a) that it actually works, and a recommended target — `backend-suite` (universal) or `house-style` (org-specific) — using the same generalization test this suite already applies to components (no project literal, works unchanged if dropped into an unrelated project). A person reviews and either approves (an agent then does the actual promotion work — generalizing the tool, stripping project literals, same rigor as `/promote-component`) or rejects it.

This is explicitly **not** a new automatic-tier capability. Per this project's own tier rule ("tier is decided by blast radius, not difficulty... content-generating and convention-setting stay explicit"), proposing a promotion is read-only and could reasonably be `auto`; performing one is foundational and convention-setting, and stays `explicit` — no different from how `/promote-component` already works for components today.

## 4. Alternatives considered

- **Do nothing — leave project-owned tooling unverified and promotion manual.** Cheapest, but leaves the exact asymmetry problem 1 describes standing, and the suite keeps growing only as fast as a person happens to notice a pattern.
- **Extend maturity to project tooling, skip the promotion pipeline.** A smaller, safer first step — gets the evidence discipline everywhere without touching how the suite grows. Worth considering as a phased first cut (see §6, Sequencing note) rather than building both at once.
- **Build the promotion pipeline without the evidence extension.** Rejected — promoting a tool without any evidence it actually works would be promoting an assertion, which is the exact failure mode this whole proposal exists to close. Evidence has to come first or alongside.
- **Let the LLM promote autonomously above some usage threshold, no human gate.** Rejected outright — directly conflicts with this project's own standing rule that a brand-new, high-blast-radius convention decision is never made without an explicit human go-ahead.

## 5. Drawbacks and risks

- **False-positive convergence detection.** Two tools that look structurally similar may serve genuinely different purposes (the same risk `audit_promotion_candidates` already carries for components, mitigated there by requiring a human to confirm via `--update-baseline`). The promotion proposal step exists specifically to catch this before anything is generalized — but a noisy detector that proposes too often will get ignored, the same failure mode this project has already learned about mechanized judgment (`docs/ROADMAP.md`'s "mechanising the check produces confident nonsense" finding).
- **Verifying prose skills is inherently weaker than verifying scripts.** Most project-local skills are LLM instructions, not deterministic code — "verified" for a skill can only ever mean "ran without erroring, contract still matches," never "does the right thing." This has to be stated plainly in the evidence file itself, or it quietly overclaims — the same trap A1's own "what verify.py must NOT do" section already warns about for suite audits.
- **Scope creep risk.** This proposal touches the profile schema, `verify.py` (not yet built), the catalogue, and a new detection mechanism modeled on two existing audits. Building all of it at once is a large, high-blast-radius effort; phasing matters (see §6).
- **A promoted tool needs an owner.** Once something moves from one project into the universal suite, who maintains it if the originating project's needs diverge from the suite's? Not addressed here — needs its own answer before the pipeline ships.

## 6. Impact

| Area | Impact |
|---|---|
| Backward compatibility | Additive only — new optional profile fields, no existing behavior changes for a project that doesn't opt in |
| Existing consumers (mobile, portal) | Neither currently has evidence files or the new manifest pointers; adopting this needs a small profile update in each, same as #48/#61's manifests already need |
| Roadmap Workstream A | Extends A1/A2 rather than replacing them — A1 still needs to exist first regardless of whether this proposal is accepted |
| `audit_promotion_candidates` / `audit_reinvented_components` | The convergence-detection half of §3b reuses their approach, applied to a new target (`.claude/commands/`/`.claude/agents/` instead of Dart widgets) — likely a new sibling script, not a rewrite of either |
| Tier/blast-radius policy | No exception requested — promotion *proposals* are read-only (`auto`-eligible); promotion *execution* stays `explicit`, consistent with existing rules |
| Security / secrets | None identified — no new external surface, no new credentials |

## 7. Open questions

- ~~What counts as "real, repeated use" for the reuse-signal trigger?~~ **Resolved by research (recorded in RFC-0001 §8):** Claude Code's plugin hooks only fire on tool calls, never on skill/command invocation — so per-invocation frequency is not mechanically observable for prose skills with current tooling, full stop, not a gap this suite can close by building more infrastructure. §3b is updated accordingly: the reuse signal now applies only to script-backed tools (piggybacking on §3a's evidence files, which already carry a timestamp), and convergence is the sole trigger for prose skills — the more common and harder case. A real per-invocation tracking mechanism would need a Claude Code harness feature that doesn't exist yet; revisit if one ships.
- ~~Does convergence detection need a manifest of "what every consumer project's tooling looks like," or can it work by directly reading each project's `.claude/commands/`/`.claude/agents/` on demand?~~ **Resolved in §8:** on-demand reads, local evidence per project, no synced cross-project manifest.
- ~~Who owns a promoted tool going forward~~ — the original project, the suite maintainer, or shared? **Resolved in §8:** the suite, going forward, credited to its origin. What happens if the originating project's needs later diverge from the suite's stays genuinely open — no case has happened yet to answer it well, and guessing now risks the same "confident nonsense" this project has already been burned by. Revisit when a real divergence occurs.
- ~~Should evidence for project-owned skills live in that project's own `.backend-suite/evidence/`, or somewhere the suite itself can see across all consumers?~~ **Resolved in §8:** local per project; read-time aggregation for convergence detection, consistent with how the decision-log query tool was built — no synced central file.
- ~~Sequencing: should this ship as one effort, or phased?~~ **Resolved in §8:** phased, and gated — §3b does not start until §3a has surfaced at least one real candidate. Building a promotion pipeline against zero real usage data is exactly the failure mode `docs/ROADMAP.md` already documented ("mechanising the check produces confident nonsense").

## 8. Decision

**Accepted, phased, gated on Workstream A1.** Decided 2026-09-14.

Both halves of this proposal explicitly depend on `verify.py` (roadmap A1), which does not exist yet. Accepting this RFC does not authorize starting implementation now — it fixes the *design* A2 should build to once A1 lands, so the work isn't re-derived later.

1. **§3a (evidence extended to project-owned tooling) is approved as written.** Once A1/A2 exist for this suite's own components, extend the same mechanism to a project's bespoke skills/agents. Low incremental risk — same mechanism, wider target.
2. **§3b (the promotion pipeline) is approved in design, gated in time.** It does not begin until §3a has been running long enough to surface at least one real promotion candidate (a genuine convergence hit, or a script-backed tool with real evidence-file usage history). No building it speculatively against synthetic or zero data.
3. **Three of the four open questions in §7 are resolved now** (see the strikethroughs above) rather than deferred again: no synced cross-project manifest — read each project on demand; a promoted tool becomes the suite's own going forward, credited to its origin; evidence stays local per project with read-time aggregation, not a central file.
4. **One question stays genuinely open:** what happens if a promoted tool's needs diverge from the originating project's over time. No real case exists yet to answer this well — resolve it when one actually happens, not in the abstract.

This decision does not create a tracking item of its own — implementation is sequenced behind roadmap Workstream A, which already has its own tracking (`docs/ROADMAP.md`, Workstream A). Issue #75 stays open as the record of this decision and its reasoning until A1 lands and §3a work actually begins.

---

_Last updated: 2026-09-14_
