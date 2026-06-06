/**
 * Shared LaTeX parsing + KaTeX rendering helpers for LatexRenderer.
 */
import katex from "katex";

const CJK_RUN =
  /[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff]/g;

const MATH_SEGMENT =
  /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g;

export type LatexSegment = {
  type: "text" | "inline" | "block";
  content: string;
};

/** Wrap bare CJK runs in \\text{…} so KaTeX can render mixed Chinese + math. */
export function prepareMathLatex(latex: string): string {
  if (!CJK_RUN.test(latex)) return latex;
  CJK_RUN.lastIndex = 0;
  return latex.replace(CJK_RUN, (run) => `\\text{${run}}`);
}

export function parseLatexSegments(text: string): LatexSegment[] {
  const parts: LatexSegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;

  const pattern = new RegExp(MATH_SEGMENT.source, "g");
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) {
      parts.push({ type: "text", content: text.slice(last, m.index) });
    }
    const raw = m[0];
    if (raw.startsWith("\\[") || raw.startsWith("$$")) {
      parts.push({ type: "block", content: raw.slice(2, -2).trim() });
    } else {
      const inner = raw.startsWith("\\(")
        ? raw.slice(2, -2)
        : raw.slice(1, -1);
      parts.push({ type: "inline", content: inner.trim() });
    }
    last = m.index + raw.length;
  }

  if (last < text.length) {
    parts.push({ type: "text", content: text.slice(last) });
  }
  return parts;
}

export function renderLatexHtml(src: string, display: boolean): string {
  const opts = {
    displayMode: display,
    throwOnError: true,
    trust: false,
  } as const;

  try {
    return katex.renderToString(src, opts);
  } catch {
    try {
      return katex.renderToString(prepareMathLatex(src), opts);
    } catch {
      return "";
    }
  }
}

export function renderLatexSegment(
  src: string,
  display: boolean
): { html: string | null; fallback: string | null } {
  const html = renderLatexHtml(src, display);
  if (html) return { html, fallback: null };
  return { html: null, fallback: src };
}
