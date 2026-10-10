// Custom heading hierarchy + spacing for the client-readiness PDF.
// Sans-serif throughout (Helvetica Neue body, Avenir Next headings) for a
// clean, modern, professional look with clear size/weight/color contrast
// between levels -- closer to the MD's own visual hierarchy than the
// pandoc/typst default (which renders every heading level in one weight).

#let accent = rgb("#1f4e5f")
#let rule-color = rgb("#c7d2d6")

#show heading.where(level: 1): it => {
  v(20pt)
  text(font: "Avenir Next", weight: 700, size: 19pt, fill: accent)[#it.body]
  v(4pt)
  line(length: 100%, stroke: 1pt + rule-color)
  v(10pt)
}

#show heading.where(level: 2): it => {
  v(14pt)
  text(font: "Avenir Next", weight: 600, size: 14pt, fill: accent)[#it.body]
  v(8pt)
}

#show heading.where(level: 3): it => {
  v(10pt)
  text(font: "Avenir Next", weight: 600, size: 12pt, fill: rgb("#3a3a3a"))[#it.body]
  v(6pt)
}

#set text(font: "Helvetica Neue", size: 10.5pt, fill: rgb("#1a1a1a"))
#set par(leading: 0.65em, justify: false)
#set list(marker: text(fill: accent)[•], indent: 4pt, spacing: 8pt)
#set enum(indent: 4pt, spacing: 8pt)

// Typst's #table() defaults to CENTERED cell content unless every column's
// alignment is set explicitly -- pandoc emits `align: (auto, auto, ...)` for
// markdown tables with no `:---` alignment markers, and "auto" resolves to
// center in typst's table implementation, not left. Force left alignment on
// every cell explicitly; without this, all table text renders centered,
// which reads as amateurish in a business document.
#show table.cell: set align(left)
#show table.cell: set text(size: 9.5pt)
#show table.cell.where(y: 0): set text(weight: 700, fill: accent)
// Neither pandoc's generated tables nor the raw typst passthrough tables in
// this doc specify a stroke, so without an explicit default here every table
// renders with no grid lines at all -- reads as loose aligned text, not a
// table. A light, low-contrast rule on every cell edge is enough to read as
// "table" without competing with the accent-colored header row.
#set table(inset: (x: 8pt, y: 7pt), stroke: 0.5pt + rule-color)

#show strong: set text(weight: 700, fill: rgb("#0d2b35"))
