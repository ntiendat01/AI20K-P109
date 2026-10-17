import { describe, expect, it } from "vitest";
import { formatComparisonMoney, parseReviewMoney } from "./utils";

describe("money formatting", () => {
  it("parses Vietnamese grouped amounts", () => {
    expect(parseReviewMoney("1.250.000")).toBe(1_250_000);
    expect(parseReviewMoney("1.250,50")).toBe(1250.5);
  });

  it("renders invalid comparison values as an em dash", () => {
    expect(formatComparisonMoney("invalid")).toBe("—");
  });
});
