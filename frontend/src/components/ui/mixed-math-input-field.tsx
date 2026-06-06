/**
 * Mixed text + math editor (MathLive) — type naturally and insert formulas inline.
 * @see https://mathlive.io/mathfield/guides/interacting/
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { MathfieldElement } from "mathlive";
import { Sigma, Type } from "lucide-react";
import "mathlive/static.css";
import "mathlive/fonts.css";
import "mathlive";

import { cn } from "@/lib/utils";

type InputMode = "text" | "math";

interface MixedMathInputFieldProps {
  value: string;
  onChange: (latex: string) => void;
  onSubmit?: () => void;
  className?: string;
  id?: string;
  disabled?: boolean;
  variant?: "problem" | "chat";
  /** Accessible name for the math editor. */
  "aria-label"?: string;
  /** Plain-text hint shown when the field is empty. */
  placeholder?: string;
}

function readInputMode(mf: MathfieldElement): InputMode {
  return mf.mode === "math" ? "math" : "text";
}

export default function MixedMathInputField({
  value,
  onChange,
  onSubmit,
  className,
  id = "mixed-math-input",
  disabled = false,
  variant = "problem",
  "aria-label": ariaLabel = "问题或回复输入",
  placeholder = "输入文字，或切换到公式模式插入数学表达式…",
}: MixedMathInputFieldProps) {
  const ref = useRef<MathfieldElement | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>("text");
  const isEmpty = !value.trim();

  useEffect(() => {
    const mf = ref.current;
    if (!mf) return;
    if (mf.value !== value) mf.value = value;
    mf.placeholder = "";
    mf.readOnly = disabled;
    setInputMode(readInputMode(mf));
  }, [value, disabled]);

  useEffect(() => {
    const mf = ref.current;
    if (!mf) return;

    const syncMode = () => setInputMode(readInputMode(mf));
    mf.addEventListener("mode-change", syncMode);
    return () => mf.removeEventListener("mode-change", syncMode);
  }, []);

  const switchToMode = useCallback(
    (mode: InputMode) => {
      const mf = ref.current;
      if (!mf || disabled) return;
      mf.focus();
      mf.executeCommand(["switchMode", mode]);
      setInputMode(mode);
    },
    [disabled]
  );

  const handleKeyDown = useCallback(
    (evt: KeyboardEvent<MathfieldElement>) => {
      if (variant !== "chat" || !onSubmit || disabled) return;
      if (evt.key === "Enter" && !evt.shiftKey) {
        evt.preventDefault();
        onSubmit();
      }
    },
    [variant, onSubmit, disabled]
  );

  return (
    <div className={cn("relative space-y-2", className)}>
      {isEmpty && (
        <div
          className={cn(
            "pointer-events-none absolute inset-x-0 top-0 z-[1] flex items-start px-4 py-3 text-sm text-gray-400",
            variant === "chat" && "items-center"
          )}
          aria-hidden
        >
          {placeholder}
        </div>
      )}

      <div className="flex gap-2">
        <math-field
          ref={ref}
          id={id}
          aria-label={ariaLabel}
          className={cn(
            "math-mixed-field flex-1",
            variant === "chat" && "math-mixed-field--chat",
            variant === "problem" && "math-mixed-field--problem",
            inputMode === "math" && "math-mixed-field--math-active"
          )}
          math-virtual-keyboard-policy="auto"
          smart-fence="on"
          smart-superscript="on"
          default-mode="text"
          onInput={(evt: FormEvent<MathfieldElement>) => {
            const native = evt.nativeEvent;
            if ("isComposing" in native && native.isComposing) return;
            onChange(evt.currentTarget.value);
          }}
          onKeyDown={handleKeyDown}
        />

        <div
          role="group"
          aria-label="输入模式"
          className={cn(
            "flex h-12 shrink-0 overflow-hidden rounded-xl border border-gray-200 bg-gray-50",
            variant === "problem" && "self-start"
          )}
        >
          <button
            type="button"
            onClick={() => switchToMode("text")}
            disabled={disabled}
            aria-pressed={inputMode === "text"}
            title="切换到文字输入"
            className={cn(
              "flex items-center justify-center gap-1 px-3 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500",
              "disabled:cursor-not-allowed disabled:opacity-50",
              inputMode === "text"
                ? "bg-white text-violet-700 shadow-sm"
                : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            )}
          >
            <Type className="h-3.5 w-3.5" aria-hidden />
            <span>文字</span>
          </button>
          <button
            type="button"
            onClick={() => switchToMode("math")}
            disabled={disabled}
            aria-pressed={inputMode === "math"}
            title="切换到公式输入"
            className={cn(
              "flex items-center justify-center gap-1 border-l border-gray-200 px-3 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500",
              "disabled:cursor-not-allowed disabled:opacity-50",
              inputMode === "math"
                ? "bg-violet-600 text-white"
                : "text-gray-500 hover:bg-violet-50 hover:text-violet-700"
            )}
          >
            <Sigma className="h-3.5 w-3.5" aria-hidden />
            <span>公式</span>
          </button>
        </div>
      </div>
    </div>
  );
}
