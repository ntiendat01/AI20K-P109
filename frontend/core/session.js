import { storageKey, flashKey } from "../config/constants.js";

export function getSession() {
  try { return JSON.parse(localStorage.getItem(storageKey)); } catch { return null; }
}

export function setSession(session) { localStorage.setItem(storageKey, JSON.stringify(session)); }

export function setFlash(message, tone = "success") {
  sessionStorage.setItem(flashKey, JSON.stringify({ message, tone }));
}

export function takeFlash() {
  try {
    const flash = JSON.parse(sessionStorage.getItem(flashKey));
    sessionStorage.removeItem(flashKey);
    return flash;
  } catch { return null; }
}
