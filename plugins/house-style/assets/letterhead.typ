// Org letterhead — standard header/footer for every client-facing PDF
// exported from this repo's pandoc+typst pipeline.
//
// This file ships brand-neutral. Fill in the `org*` values below and, for a
// logo, drop your own PNG at `.claude/commands/assets/logo.png` and set
// `orgLogoPath` to that path. With `orgLogoPath: none` the header falls back
// to the org name set as text, so the file compiles out of the box.
//
// Usage: pass this file to `--include-in-header` ALONGSIDE a document's own
// content-styling include (e.g. client-readiness-style.typ) — this file only
// owns the page header/footer band; it does not touch heading/table/text
// styling, so it composes with any content style file in this repo.
//
//   pandoc doc.md -o out.pdf --pdf-engine=typst \
//     --include-in-header=.claude/commands/letterhead.typ \
//     --include-in-header=.claude/commands/client-readiness-style.typ \
//     -V mainfont="Helvetica Neue"

#let orgName = "Your Organisation"
#let orgUrl = "www.example.com"
#let orgOffices = ("City One", "City Two")
#let orgLogoPath = none // e.g. ".claude/commands/assets/logo.png"

#let letterheadNavy = rgb("#1f2937")
#let letterheadTeal = rgb("#2563eb")
#let letterheadGray = rgb("#6b6b6b")

// Typst resolves relative image paths against the main document being
// compiled, not against this include file's own location — so a logo path is
// relative to wherever `pandoc` is invoked from. The documented export
// command always runs from the repo root, so use a repo-root-relative path.
#let orgLogo = if orgLogoPath == none {
  text(size: 16pt, weight: 700, fill: letterheadNavy)[#orgName]
} else {
  image(orgLogoPath, width: 130pt)
}

// Footer layout math (why the numbers below are what they are):
// `place(bottom + ...)` inside the footer anchors to the true bottom of the
// PAGE, not to a small box sized to the footer text's own content -- so a
// naive `footer-descent` (which shifts the whole footer down from that
// already-bottom-anchored position) pushes the bottom rule's bottom edge
// past the physical page edge, and the part that falls outside gets clipped
// by the paper trim rather than wrapped or scaled. That's the "cut off at
// the bottom" bug: footer-descent was adding a downward push on top of an
// element that was already flush with the page's true bottom.
// Fix: footer-descent stays at 0 (nothing pushes bottom-anchored content past
// the edge), the bottom rule is pulled up from true bottom by an explicit
// dy so there's breathing room above the paper edge, and bottom margin is
// generous enough that the text lines (anchored to the TOP of the footer
// region) can never collide with the bottom rule (anchored near the
// BOTTOM of that same region) regardless of how the footer's box is sized.
#set page(
  margin: (top: 90pt, bottom: 110pt, left: 54pt, right: 54pt),
  header: align(left)[#orgLogo],
  header-ascent: 30pt,
  footer: context {
    set text(font: "Helvetica Neue", size: 8.5pt, fill: letterheadNavy)
    place(top + left, dy: 14pt)[
      #orgOffices.join([ #h(4pt) | #h(4pt) ])
    ]
    place(top + left, dy: 32pt)[#text(weight: 700)[#orgUrl]]
    place(top + right, dy: 32pt)[Page #counter(page).display()]
    // Accent rule along the bottom of the footer band.
    place(bottom + left, dy: -10pt, line(length: 100%, stroke: 2pt + letterheadTeal))
  },
  footer-descent: 0pt,
)
