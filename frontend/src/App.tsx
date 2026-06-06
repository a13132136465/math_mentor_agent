import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AppLayout from "@/components/layout/AppLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";

import { lazy, Suspense } from "react";
const ProblemPage     = lazy(() => import("@/pages/ProblemPage"));
const ChatPage        = lazy(() => import("@/pages/ChatPage"));
const ReportPage      = lazy(() => import("@/pages/ReportPage"));
const ExercisesPage   = lazy(() => import("@/pages/ExercisesPage"));
const ExerciseSetPage = lazy(() => import("@/pages/ExerciseSetPage"));
const SettingsPage    = lazy(() => import("@/pages/SettingsPage"));

function PageFallback() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      {t("common.loading")}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route
            path="problem"
            element={
              <Suspense fallback={<PageFallback />}>
                <ProblemPage />
              </Suspense>
            }
          />
          <Route
            path="chat/:sessionId?"
            element={
              <Suspense fallback={<PageFallback />}>
                <ChatPage />
              </Suspense>
            }
          />
          <Route
            path="report"
            element={
              <Suspense fallback={<PageFallback />}>
                <ReportPage />
              </Suspense>
            }
          />
          <Route
            path="exercises"
            element={
              <Suspense fallback={<PageFallback />}>
                <ExercisesPage />
              </Suspense>
            }
          />
          <Route
            path="exercises/:setId"
            element={
              <Suspense fallback={<PageFallback />}>
                <ExerciseSetPage />
              </Suspense>
            }
          />
          <Route
            path="settings"
            element={
              <Suspense fallback={<PageFallback />}>
                <SettingsPage />
              </Suspense>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
