/**
 * Helpers for mixed text + math input:
 * MathLive LaTeX ↔ API strings with \\( … \\) delimiters.
 */

const MATH_SEGMENT =
  /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g;

/** Escape plain text for use inside MathLive \\text{…}. */
function escapeTextForLatex(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\{/g, "\\{").replace(/\}/g, "\\}");
}

/** Unescape content from a \\text{…} block. */
function unescapeTextFromLatex(text: string): string {
  return text.replace(/\\([{}\\])/g, "$1");
}

/**
 * Convert stored problem / message text (with \\( … \\) delimiters)
 * into MathLive mixed text+math LaTeX.
 */
export function deserializeApiToMathlive(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";

  const parts: string[] = [];
  let last = 0;
  let foundMath = false;
  let m: RegExpExecArray | null;

  const pattern = new RegExp(MATH_SEGMENT.source, "g");
  while ((m = pattern.exec(trimmed)) !== null) {
    foundMath = true;
    if (m.index > last) {
      const plain = trimmed.slice(last, m.index);
      if (plain) parts.push(`\\text{${escapeTextForLatex(plain)}}`);
    }
    const raw = m[0];
    let inner: string;
    if (raw.startsWith("\\[")) inner = raw.slice(2, -2).trim();
    else if (raw.startsWith("\\(")) inner = raw.slice(2, -2).trim();
    else if (raw.startsWith("$$")) inner = raw.slice(2, -2).trim();
    else inner = raw.slice(1, -1).trim();
    parts.push(inner);
    last = m.index + raw.length;
  }

  if (last < trimmed.length) {
    parts.push(`\\text{${escapeTextForLatex(trimmed.slice(last))}}`);
  }

  if (!foundMath) {
    // Legacy pure-math input (no delimiters) — treat whole string as math.
    if (/\\[a-zA-Z]/.test(trimmed)) return trimmed;
    return `\\text{${escapeTextForLatex(trimmed)}}`;
  }

  return parts.join("");
}

/**
 * Convert MathLive mixed text+math LaTeX into API / display format
 * with \\( … \\) inline delimiters.
 */
export function serializeMathliveToApi(latex: string): string {
  const trimmed = latex.trim();
  if (!trimmed) return "";

  const parts: string[] = [];
  let remaining = trimmed;

  const textPattern = /^\\text\{((?:[^{}]|\{[^{}]*\})*)\}/;

  while (remaining.length > 0) {
    const textMatch = remaining.match(textPattern);
    if (textMatch && textMatch.index === 0) {
      const plain = unescapeTextFromLatex(textMatch[1]);
      if (plain) parts.push(plain);
      remaining = remaining.slice(textMatch[0].length);
      continue;
    }

    const nextText = remaining.search(/\\text\{/);
    const mathPart =
      nextText === -1 ? remaining : remaining.slice(0, nextText);
    const mathTrimmed = mathPart.trim();
    if (mathTrimmed) {
      parts.push(`\\( ${mathTrimmed} \\)`);
    }
    remaining = nextText === -1 ? "" : remaining.slice(nextText);
  }

  return parts.join(" ").replace(/\s+/g, " ").trim();
}

/** Whether serialized text contains at least one math segment. */
export function hasMathContent(apiText: string): boolean {
  return new RegExp(MATH_SEGMENT.source).test(apiText);
}

/** Character count for validation (serialized, human-facing text). */
export function effectiveContentLength(apiText: string): number {
  return apiText.trim().length;
}

// ── Legacy helpers (kept for backward compatibility) ─────────────

/** Pull LaTeX out of example / stored strings that use \\( … \\) wrappers. */
export function extractLatexFromProblem(problem: string): string {
  const inline = problem.match(/\\\(([\s\S]*?)\\\)/);
  if (inline) return inline[1].trim();
  const block = problem.match(/\\\[([\s\S]*?)\\\]/);
  if (block) return block[1].trim();
  return problem.trim();
}

/** Text before the first \\( … \\) block, e.g. "Evaluate" in example cards. */
export function extractInstructionFromProblem(problem: string): string {
  const idx = problem.indexOf("\\(");
  if (idx <= 0) return "";
  return problem.slice(0, idx).trim();
}

/** @deprecated Use serializeMathliveToApi instead. */
export function formatProblemText(instruction: string, latex: string): string {
  const body = latex.trim();
  if (!body) return "";
  const math = `\\( ${body} \\)`;
  const prefix = instruction.trim();
  return prefix ? `${prefix} ${math}` : math;
}
