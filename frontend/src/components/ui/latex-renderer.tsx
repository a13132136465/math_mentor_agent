/**
 * LatexRenderer — renders a string that may contain both plain text and
 * LaTeX delimiters (\( … \) inline, \[ … \] block).
 *
 * Falls back to plain text if KaTeX throws (no red error styling).
 */
import { memo, useMemo } from "react";
import "katex/dist/katex.min.css";
import { cn } from "@/lib/utils";
import { parseLatexSegments, renderLatexSegment } from "@/lib/latex-render";

interface Props {
  children: string;
  className?: string;
  displayMode?: boolean;
}

function LatexRenderer({ children, className, displayMode }: Props) {
  const segments = useMemo(() => {
    if (displayMode) {
      return [{ type: "block" as const, content: children }];
    }
    return parseLatexSegments(children);
  }, [children, displayMode]);

  return (
    <span className={cn("latex-renderer leading-relaxed", className)}>
      {segments.map((seg, i) => {
        if (seg.type === "text") {
          return <span key={i}>{seg.content}</span>;
        }
        const { html, fallback } = renderLatexSegment(
          seg.content,
          seg.type === "block"
        );
        if (html) {
          return (
            <span
              key={i}
              className="katex-safe"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        }
        return (
          <span key={i} className="font-mono text-[0.92em]">
            {fallback}
          </span>
        );
      })}
    </span>
  );
}

export default memo(LatexRenderer);
