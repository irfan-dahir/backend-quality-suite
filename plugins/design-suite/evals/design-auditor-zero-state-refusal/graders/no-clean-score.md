---
type: regex
pattern: "Compliance Score:\\s*(100|9[0-9]|8[0-9])\\s*/\\s*100"
match: not_contains
target: last_message
---
