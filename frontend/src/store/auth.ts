import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { StudentProfile } from "@/lib/api";

interface AuthState {
  token: string | null;
  profile: StudentProfile | null;
  setToken: (token: string) => void;
  setProfile: (profile: StudentProfile) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      profile: null,
      setToken: (token) => set({ token }),
      setProfile: (profile) => set({ profile }),
      logout: () => set({ token: null, profile: null }),
    }),
    { name: "mathmentor-auth" }
  )
);
