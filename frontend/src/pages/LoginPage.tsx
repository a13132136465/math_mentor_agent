import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { GraduationCap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import LanguageSwitcher from "@/components/layout/LanguageSwitcher";
import { useAuthStore } from "@/store/auth";
import { authApi, meApi } from "@/lib/api";
import {
  getGoogleClientId,
  renderGoogleSignInButton,
  type GoogleCredentialResponse,
} from "@/lib/google-auth";
import i18n from "@/i18n";

async function finishLogin(
  accessToken: string,
  setToken: (t: string) => void,
  setProfile: (p: Awaited<ReturnType<typeof meApi.profile>>["data"]) => void
) {
  setToken(accessToken);
  const profileRes = await meApi.profile();
  setProfile(profileRes.data);
  const prefLocale = profileRes.data.preferences.locale;
  if (prefLocale === "en" || prefLocale === "zh") {
    await i18n.changeLanguage(prefLocale);
  }
}

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setToken, setProfile } = useAuthStore();
  const googleButtonRef = useRef<HTMLDivElement>(null);

  const [devLoading, setDevLoading] = useState(false);
  const [devError, setDevError] = useState<string | null>(null);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [googleConfigured, setGoogleConfigured] = useState(!!getGoogleClientId());

  const handleGoogleCredential = useCallback(
    async (response: GoogleCredentialResponse) => {
      setGoogleLoading(true);
      setGoogleError(null);
      try {
        const { data } = await authApi.google(response.credential);
        await finishLogin(data.access_token, setToken, setProfile);
        navigate("/");
      } catch {
        setGoogleError(t("login.googleError"));
      } finally {
        setGoogleLoading(false);
      }
    },
    [navigate, setProfile, setToken, t]
  );

  useEffect(() => {
    const clientId = getGoogleClientId();
    setGoogleConfigured(!!clientId);
    if (!clientId || !googleButtonRef.current) {
      return;
    }

    let cancelled = false;
    renderGoogleSignInButton(googleButtonRef.current, (cred) => {
      if (!cancelled) {
        void handleGoogleCredential(cred);
      }
    }).catch(() => {
      if (!cancelled) {
        setGoogleError(t("login.googleLoadError"));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [handleGoogleCredential, t]);

  async function handleDevLogin() {
    setDevLoading(true);
    setDevError(null);
    try {
      const { data } = await authApi.devLogin();
      await finishLogin(data.access_token, setToken, setProfile);
      navigate("/");
    } catch {
      setDevError(t("login.devError"));
    } finally {
      setDevLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-violet-50 via-white to-indigo-50">
      <div className="absolute right-4 top-4 sm:right-8 sm:top-8">
        <LanguageSwitcher />
      </div>

      <div className="w-full max-w-md px-4">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-violet-600 shadow-lg shadow-violet-200">
            <GraduationCap className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">MathMentor</h1>
          <p className="mt-2 text-muted-foreground">{t("login.tagline")}</p>
        </div>

        <Card>
          <CardHeader className="text-center">
            <CardTitle>{t("login.welcome")}</CardTitle>
            <CardDescription>{t("login.subtitle")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {googleConfigured ? (
              <div className="flex min-h-10 w-full flex-col items-center gap-2">
                <div ref={googleButtonRef} className="flex w-full justify-center" />
                {googleLoading && (
                  <p className="text-xs text-muted-foreground">{t("login.loggingIn")}</p>
                )}
              </div>
            ) : (
              <Button className="w-full gap-3" variant="outline" disabled>
                <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                {t("login.google")}
              </Button>
            )}

            {!googleConfigured && (
              <p className="text-center text-xs text-muted-foreground">
                {t("login.oauthNotice")}
              </p>
            )}

            {googleError && (
              <p role="alert" className="text-center text-xs text-red-500">
                {googleError}
              </p>
            )}

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">{t("common.or")}</span>
              </div>
            </div>

            <Button className="w-full" onClick={handleDevLogin} disabled={devLoading || googleLoading}>
              {devLoading ? t("login.loggingIn") : t("login.devLogin")}
            </Button>
            {devError && (
              <p role="alert" className="text-center text-xs text-red-500">
                {devError}
              </p>
            )}

            <p className="text-center text-xs text-muted-foreground">
              {t("login.terms")}
            </p>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          {t("login.footer")}
        </p>
      </div>
    </div>
  );
}
