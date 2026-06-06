/**
 * Google Identity Services (GIS) — credential callback for React SPA.
 */

export type GoogleCredentialResponse = {
  credential: string;
  select_by?: string;
};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: Record<string, string | number | boolean>
          ) => void;
          prompt: () => void;
        };
      };
    };
  }
}

const GIS_SCRIPT = "https://accounts.google.com/gsi/client";

let scriptPromise: Promise<void> | null = null;

export function getGoogleClientId(): string | undefined {
  const id = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  return id && id.trim().length > 0 ? id.trim() : undefined;
}

export function loadGoogleIdentityScript(): Promise<void> {
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (scriptPromise) {
    return scriptPromise;
  }

  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${GIS_SCRIPT}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("GIS script failed")));
      return;
    }

    const script = document.createElement("script");
    script.src = GIS_SCRIPT;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Identity Services"));
    document.head.appendChild(script);
  });

  return scriptPromise;
}

export async function renderGoogleSignInButton(
  container: HTMLElement,
  onCredential: (response: GoogleCredentialResponse) => void
): Promise<boolean> {
  const clientId = getGoogleClientId();
  if (!clientId) {
    return false;
  }

  await loadGoogleIdentityScript();

  if (!window.google?.accounts?.id) {
    throw new Error("Google Identity Services unavailable");
  }

  window.google.accounts.id.initialize({
    client_id: clientId,
    callback: onCredential,
    auto_select: false,
    cancel_on_tap_outside: true,
  });

  container.replaceChildren();
  window.google.accounts.id.renderButton(container, {
    type: "standard",
    theme: "outline",
    size: "large",
    text: "continue_with",
    shape: "rectangular",
    width: 360,
  });

  return true;
}
