import { FLASH_KEY, STORAGE_KEY } from "./config";
import type { FlashMessage, Session } from "./types";

export function readSession(): Session | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value ? JSON.parse(value) as Session : null;
  } catch {
    return null;
  }
}

export function writeSession(session: Session): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function setFlash(message: string, tone: FlashMessage["tone"] = "success"): void {
  sessionStorage.setItem(FLASH_KEY, JSON.stringify({ message, tone }));
}

export function takeFlash(): FlashMessage | null {
  try {
    const value = sessionStorage.getItem(FLASH_KEY);
    sessionStorage.removeItem(FLASH_KEY);
    return value ? JSON.parse(value) as FlashMessage : null;
  } catch {
    return null;
  }
}
