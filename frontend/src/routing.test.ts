import { describe, expect, it } from "vitest";
import { legacyHashToPath } from "./routing";

describe("legacy route compatibility", () => {
  it("maps the old purchase-request routes", () => {
    expect(legacyHashToPath("#/pr/pr-123")).toBe("/purchase-requests/pr-123");
    expect(legacyHashToPath("#/quotations/pr-123")).toBe("/purchase-requests/pr-123/quotations");
    expect(legacyHashToPath("#/comparison/pr-123")).toBe("/purchase-requests/pr-123/comparison");
  });

  it("ignores normal browser hashes", () => {
    expect(legacyHashToPath("#section")).toBeNull();
  });
});
