// Fixture for verify_seam.py. Not application code — do not build or lint this.
//
// CSS-in-JS: inside a tagged template literal the syntax is CSS, so properties are
// kebab-case and values end with `;`. The object-syntax checks match camelCase and
// see almost nothing here, which is why this was an under-reporting gap.
import styled, { css, createGlobalStyle } from "styled-components";
import { tokens } from "./theme";

// VIOLATIONS — raw lengths and a duration inside a template literal.
export const Panel = styled.div`
  padding: 16px;
  margin-top: 1.5rem;
  border-radius: 7px;
  transition: opacity 250ms ease-in-out;
`;

// CORRECT USAGE — must never be flagged. An interpolated token and a CSS custom
// property are both the right way to reference a token.
export const Good = styled.section`
  padding: ${tokens.spacingMd};
  gap: var(--gap-sm);
  margin: 0;
`;

// styled(Component) form, plus .attrs — the tag matcher has to handle both.
export const Wrapped = styled(Panel).attrs({ role: "group" })`
  height: 42px;
`;

// A bare css`` helper.
export const helper = css`
  gap: 13px;
`;

createGlobalStyle`
  body { line-height: 21px; }
`;

// OUTSIDE any template literal. These kebab-case strings are prose and JSX text,
// and a check that fired here would be noise — the reason the CSS patterns are
// scoped to template spans at all.
// padding: 16px; and border-radius: 7px; written in a comment
export const Caption = () => <p>Set padding: 16px; in your editor config</p>;
