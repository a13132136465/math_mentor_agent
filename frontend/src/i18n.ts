import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const STORAGE_KEY = "mathmentor-lang";

function getInitialLanguage(): string {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") return stored;
  const browser = navigator.language.toLowerCase();
  return browser.startsWith("zh") ? "zh" : "en";
}

const initialLang = getInitialLanguage();
document.documentElement.lang = initialLang === "zh" ? "zh-Hans" : "en";

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    zh: { translation: zh },
  },
  lng: initialLang,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (lng) => {
  localStorage.setItem(STORAGE_KEY, lng);
  document.documentElement.lang = lng === "zh" ? "zh-Hans" : "en";
});

export default i18n;
