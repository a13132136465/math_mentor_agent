import { useTranslation } from "react-i18next";
import { GraduationCap, User } from "lucide-react";
import LatexRenderer from "@/components/ui/latex-renderer";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/hooks/useSessionSSE";

const VERDICT_BADGE: Record<string, string> = {
  correct: "bg-emerald-50 text-emerald-700 border-emerald-200",
  partially_correct: "bg-amber-50 text-amber-700 border-amber-200",
  incorrect: "bg-red-50 text-red-700 border-red-200",
  unclear: "bg-gray-50 text-gray-600 border-gray-200",
};

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
}

export default function ChatMessageBubble({ message, isStreaming }: Props) {
  const { t } = useTranslation();
  const isStudent = message.role === "student";
  const isSystem = message.role === "system";

  if (isSystem) {
    const isError = message.content.startsWith("⚠️");
    return (
      <div className="flex justify-center py-2">
        <p
          className={cn(
            "max-w-xl rounded-lg px-4 py-2 text-xs leading-relaxed",
            isError
              ? "border border-red-200 bg-red-50 text-red-700"
              : "rounded-full bg-violet-50 px-3 py-1 text-violet-600"
          )}
        >
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <article
      aria-label={isStudent ? t("chat.yourMessage") : t("chat.tutorReply")}
      className={cn(
        "flex gap-3",
        isStudent ? "flex-row-reverse" : "flex-row"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          isStudent ? "bg-violet-100" : "bg-gray-900"
        )}
      >
        {isStudent ? (
          <User className="h-4 w-4 text-violet-600" />
        ) : (
          <GraduationCap className="h-4 w-4 text-white" />
        )}
      </div>

      <div
        className={cn(
          "max-w-[85%] space-y-1.5",
          isStudent ? "items-end text-right" : "items-start"
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
            isStudent
              ? "rounded-tr-md bg-violet-600 text-white"
              : "rounded-tl-md border border-gray-200 bg-white text-gray-800"
          )}
        >
          {isStudent ? (
            <div className="student-message-content text-left">
              <LatexRenderer>{message.content}</LatexRenderer>
            </div>
          ) : (
            <div className={cn(isStreaming && !message.content && "min-h-[1.25rem]")}>
              {message.content ? (
                <LatexRenderer>{message.content}</LatexRenderer>
              ) : isStreaming ? (
                <span className="inline-flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400" />
                </span>
              ) : null}
            </div>
          )}
        </div>

        {message.verdict && !isStudent && (
          <span
            className={cn(
              "inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize",
              VERDICT_BADGE[message.verdict] ?? VERDICT_BADGE.unclear
            )}
          >
            {message.verdict.replace(/_/g, " ")}
            {message.errorTag ? ` · ${message.errorTag.replace(/_/g, " ")}` : ""}
          </span>
        )}
      </div>
    </article>
  );
}
