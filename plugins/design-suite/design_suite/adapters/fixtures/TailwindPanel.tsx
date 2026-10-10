// Fixture for verify_seam.py. Not application code — do not build or lint this.
//
// The point of this file is the distinction the tsx adapter has to get right:
// Tailwind scale classes ARE the design system, and arbitrary values in square
// brackets bypass it. Flagging the former would report a correctly-tokenised
// codebase as entirely broken, which is worse than finding nothing.
import { tokens } from "./theme";

export const TailwindPanel = ({ label }: { label: string }) => (
  <>
    {/* CORRECT USAGE — every one of these is a scale reference and must never
        be flagged. This is the majority of a real Tailwind codebase. */}
    <div className="flex h-4 w-full items-center gap-2 p-4 text-sm rounded-md
                    duration-200 hover:bg-slate-100 md:px-6">
      {label}
    </div>

    {/* SCALE BYPASSES — each one is a finding. */}
    <div className="h-[17px] w-[240px]" />
    <div className="text-[#111827] bg-[#fff]" />
    <div className="rounded-[7px]" />
    <div className="duration-[350ms]" />

    {/* Variant and important prefixes must not hide a bypass. */}
    <div className="hover:text-[#FF0000] md:p-[13px] !gap-[7px]" />

    {/* Arbitrary value that is a function call rather than a literal. */}
    <div className="border-[rgb(17,24,39)] max-w-[calc(100%-2rem)]" />

    {/* A token reference next to a Tailwind class — neither is a finding. */}
    <div className="p-2" style={{ color: tokens.colorOnSurface }} />
  </>
);
