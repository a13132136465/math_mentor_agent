import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import i18n from "@/i18n";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPct(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function difficultyLabel(d: number): string {
  const key = `difficulty.${d}`;
  return i18n.t(key, { defaultValue: i18n.t("difficulty.3") });
}

export function difficultyColor(d: number): string {
  if (d <= 2) return "text-emerald-600 bg-emerald-50";
  if (d === 3) return "text-amber-600 bg-amber-50";
  return "text-red-600 bg-red-50";
}

export function masteryColor(score: number): string {
  if (score >= 0.7) return "text-emerald-600";
  if (score >= 0.4) return "text-amber-600";
  return "text-red-500";
}

export function masteryLabel(score: number): string {
  if (score >= 0.7) return i18n.t("mastery.proficient");
  if (score >= 0.4) return i18n.t("mastery.developing");
  return i18n.t("mastery.beginner");
}

export function topicLabel(topic: string): string {
  const key = `topics.${topic}`;
  return i18n.exists(key) ? i18n.t(key) : topic;
}

export function formatTag(tag: string): string {
  return tag.replace(/_/g, " ");
}

export function formatDateTime(iso: string): string {
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";
  return new Date(iso).toLocaleString(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
