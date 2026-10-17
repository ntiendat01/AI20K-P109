import { beforeEach, describe, expect, it } from "vitest";
import { readSession, setFlash, takeFlash, writeSession } from "./session";

describe("browser session storage", () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

  it("persists the authenticated session", () => {
    const session = { access_token: "token", user: { id: "u-1", name: "Buyer", email: "buyer@example.com", role: "procurement" as const } };
    writeSession(session);
    expect(readSession()).toEqual(session);
  });

  it("consumes flash messages once", () => {
    setFlash("Đã lưu");
    expect(takeFlash()).toEqual({ message: "Đã lưu", tone: "success" });
    expect(takeFlash()).toBeNull();
  });
});
