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
  "astronomical_dating_candidate",
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

  it("never treats a dating candidate as evidence, however exact its ephemeris", () => {
    // The sky under a candidate is computed; the match between it and the text is not.
    // Presenting the second with the weight of the first is the specific failure this
    // whole product exists to prevent.
    expect(claimStyle("astronomical_dating_candidate").isEvidence).toBe(false);
    expect(claimStyle("astronomical_dating_candidate").label).toBe("Dating candidate");
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

  // Asserted as the exact class, not a substring like "green": this matched on colour
  // names until the manuscript restyle renamed the palette (green became verdigris, red
  // became crimson), which failed the test without any behaviour changing. The class
  // name is the contract; what the design system calls that colour is its own business.
  // Values are paired around each threshold so a boundary that slips shows up here.
  it.each([
    [1, "bg-verdigris-600"],
    [0.7, "bg-verdigris-600"],
    [0.69, "bg-gold-500"],
    [0.5, "bg-gold-500"],
    [0.49, "bg-terra-500"],
    [0.3, "bg-terra-500"],
    [0.29, "bg-crimson-500"],
    [0, "bg-crimson-500"],
  ])("colours %s as %s", (value, className) => {
    expect(confidenceColor(value)).toBe(className);
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
