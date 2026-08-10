import { describe, expect, it } from "vitest";
import {
  CLAIM_STYLES,
  claimStyle,
  confidenceBand,
  confidenceColor,
  entityTypeLabel,
  formatYear,
} from "@/lib/claims";
import type { ClaimType } from "@/lib/types";

const ALL: ClaimType[] = [
  "source_text",
  "verified_history",
  "astronomical_calculation",
  "textual_analysis",
  "traditional_interpretation",
  "scholarly_interpretation",
  "ai_hypothesis",
  "uncertain",
];

describe("claim presentation", () => {
  it("styles every claim type the backend can emit", () => {
    for (const type of ALL) {
      const style = claimStyle(type);
      expect(style.label).toBeTruthy();
      expect(style.description).toBeTruthy();
      expect(style.badge).toBeTruthy();
      expect(style.icon).toBeTruthy();
    }
  });

  it("marks exactly the three evidence types as evidence", () => {
    const evidence = ALL.filter((type) => CLAIM_STYLES[type].isEvidence);
    expect(evidence.sort()).toEqual(
      ["astronomical_calculation", "source_text", "verified_history"].sort(),
    );
  });

  it("never treats a hypothesis or a tradition as evidence", () => {
    expect(claimStyle("ai_hypothesis").isEvidence).toBe(false);
    expect(claimStyle("traditional_interpretation").isEvidence).toBe(false);
    expect(claimStyle("scholarly_interpretation").isEvidence).toBe(false);
  });

  it("falls back safely for an unknown type rather than crashing", () => {
    expect(claimStyle("something_new" as ClaimType).label).toBe("Unresolved");
  });

  it("gives each type a visually distinct badge", () => {
    const badges = new Set(ALL.map((type) => CLAIM_STYLES[type].badge));
    expect(badges.size).toBe(ALL.length);
  });
});

describe("confidence", () => {
  it.each([
    [0.95, "very high"],
    [0.75, "high"],
    [0.55, "moderate"],
    [0.35, "low"],
    [0.1, "very low"],
  ])("bands %s as %s", (value, band) => {
    expect(confidenceBand(value)).toBe(band);
  });

  it("colours low confidence as a warning", () => {
    expect(confidenceColor(0.9)).toContain("green");
    expect(confidenceColor(0.2)).toContain("red");
  });
});

describe("formatting", () => {
  it("converts astronomical year numbering to BCE/CE", () => {
    expect(formatYear(2024)).toBe("2024 CE");
    expect(formatYear(1)).toBe("1 CE");
    // Year 0 is 1 BCE; year -586 is 587 BCE.
    expect(formatYear(0)).toBe("1 BCE");
    expect(formatYear(-586)).toBe("587 BCE");
  });

  it("labels entity types readably", () => {
    expect(entityTypeLabel("sacred_number")).toBe("Sacred numbers");
    expect(entityTypeLabel("astronomical_object")).toBe("Celestial objects");
    expect(entityTypeLabel("unmapped_type")).toBe("unmapped type");
  });
});
