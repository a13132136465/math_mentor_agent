import { meApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

/** Reload student profile from API and update the auth store. */
export async function refreshProfile() {
  const { data } = await meApi.profile();
  useAuthStore.getState().setProfile(data);
  return data;
}
