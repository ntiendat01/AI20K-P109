import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest, ApiError } from "./api";
import type { Session } from "./types";

const session: Session = { access_token: "token", user: { id: "u-1", name: "Buyer", email: "buyer@example.com", role: "procurement" } };

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends bearer authentication below /api/v1", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(apiRequest("/prs", session)).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/prs", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token" }) }));
  });

  it("preserves validation details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ["body", "code"], msg: "required" }] }), { status: 422 }));
    const promise = apiRequest("/prs", session);
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ status: 422, validationErrors: [{ msg: "required" }] });
  });
});
