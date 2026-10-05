import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import zhTW from "./locales/zh-TW.json";

export const SUPPORTED_LANGUAGES = ["zh-TW", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

const LANG_KEY = "dgxsp.lang";

function initialLanguage(): Language {
  const saved = typeof localStorage !== "undefined" ? localStorage.getItem(LANG_KEY) : null;
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(saved ?? "") ? (saved as Language) : "zh-TW";
}

void i18n.use(initReactI18next).init({
  resources: { "zh-TW": { translation: zhTW }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: "zh-TW",
  interpolation: { escapeValue: false },
  saveMissing: import.meta.env.DEV,
  missingKeyHandler: (_lngs, _ns, key) => {
    if (import.meta.env.DEV) console.warn(`[i18n] missing key: ${key}`);
  },
});

export function setLanguage(lang: Language): void {
  localStorage.setItem(LANG_KEY, lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
