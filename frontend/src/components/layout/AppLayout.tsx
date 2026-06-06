import { Outlet, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import Sidebar from "./Sidebar";
import { useAuthStore } from "@/store/auth";

export default function AppLayout() {
  const { t, i18n } = useTranslation();
  const token = useAuthStore((s) => s.token);
  const profile = useAuthStore((s) => s.profile);

  useEffect(() => {
    const pref = profile?.preferences.locale;
    if ((pref === "en" || pref === "zh") && i18n.language !== pref) {
      void i18n.changeLanguage(pref);
    }
  }, [profile?.preferences.locale, i18n]);

  if (!token) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <a href="#main-content" className="skip-link">
        {t("nav.skipToContent")}
      </a>
      <Sidebar />
      <main id="main-content" className="flex-1 overflow-y-auto" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
