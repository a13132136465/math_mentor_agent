import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard, PenLine, MessageSquare,
  BarChart3, BookOpen, LogOut, GraduationCap, Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import LlmProviderSwitch from "@/components/layout/LlmProviderSwitch";
import LanguageSwitcher from "@/components/layout/LanguageSwitcher";

const NAV_KEYS = [
  { to: "/",          key: "nav.dashboard",       icon: LayoutDashboard },
  { to: "/problem",   key: "nav.newProblem",      icon: PenLine },
  { to: "/chat",      key: "nav.tutorChat",       icon: MessageSquare },
  { to: "/exercises", key: "nav.practiceDrills",  icon: BookOpen },
  { to: "/report",    key: "nav.learningReport",  icon: BarChart3 },
  { to: "/settings",  key: "nav.settings",        icon: Settings },
] as const;

export default function Sidebar() {
  const { t } = useTranslation();
  const { profile, logout } = useAuthStore();
  const navigate = useNavigate();

  const initials = profile?.display_name
    .split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2) ?? "MM";

  return (
    <aside
      aria-label={t("nav.ariaLabel")}
      className="flex h-screen w-64 flex-col border-r border-gray-200 bg-white"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-6 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600">
          <GraduationCap className="h-4 w-4 text-white" />
        </div>
        <span className="text-lg font-bold tracking-tight">MathMentor</span>
      </div>

      <div className="h-px w-full bg-gray-200" />

      {/* Navigation */}
      <nav aria-label={t("nav.mainNav")} className="flex-1 space-y-1 px-3 py-4">
        {NAV_KEYS.map(({ to, key, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex min-h-12 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
                isActive
                  ? "bg-violet-50 text-violet-700"
                  : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {t(key)}
          </NavLink>
        ))}
      </nav>

      <div className="h-px w-full bg-gray-200" />

      <div className="px-4 py-3">
        <LanguageSwitcher variant="compact" />
      </div>

      <div className="h-px w-full bg-gray-200" />

      <LlmProviderSwitch />

      <div className="h-px w-full bg-gray-200" />

      {/* User footer */}
      <div className="flex items-center gap-3 px-4 py-4">
        <Avatar className="h-8 w-8">
          <AvatarImage src={profile?.avatar_url ?? undefined} />
          <AvatarFallback className="text-xs bg-violet-100 text-violet-700">{initials}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{profile?.display_name ?? t("common.student")}</p>
          <p className="truncate text-xs text-gray-500">{profile?.email ?? ""}</p>
        </div>
        <button
          type="button"
          onClick={() => { logout(); navigate("/login"); }}
          className="touch-target shrink-0 rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2"
          aria-label={t("nav.logout")}
        >
          <LogOut className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </aside>
  );
}
