// Fixture for verify_seam.py. Not application code — do not build or lint this.
// Each line below is chosen to exercise one engine behaviour; see the expectations
// in verify_seam.py.
import { tokens } from "./theme";

export const Card = ({ title }: { title: string }) => (
  <div style={{ padding: 16, background: "#f3f9fc", borderRadius: 8 }}>
    <span style={{ color: tokens.colorOnSurface }}>{title}</span>
    <div style={{ transition: "opacity 250ms ease-in-out" }} />
    <div style={{ color: "var(--brand-primary)" }} />

    {/* Regression case for the false negative tsx.py used to document as unfixed:
        a token in one property must not suppress a raw literal in the next.
        `marginTop` here went unreported for exactly that reason. */}
    <div style={{ color: tokens.colorOnSurface, marginTop: "12px" }} />

    {/* Zero is idiomatic, not a tokenisation failure — must stay unflagged. */}
    <div style={{ margin: 0, padding: 0 }} />
  </div>
);
