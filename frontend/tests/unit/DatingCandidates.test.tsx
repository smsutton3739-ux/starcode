import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { DatingCandidates } from "@/components/DatingCandidates";
import type { Claim } from "@/lib/types";

/**
 * The promise this component carries: a candidate date is a proposal you can argue with.
 *
 * The assertions are about what a reader can see, not about markup. A candidate that
 * shows its matches and hides its misses would render perfectly and be dishonest, so the
 * misses are what most of this file checks.
 */

function candidate(overrides: Partial<Claim> = {}): Claim {
  return {
    id: "claim-1",
    section: "dating_candidates",
    claim_type: "astronomical_dating_candidate",
    statement: "28 May 585 BCE is a candidate: its sky matches 1 of 2 criteria (fit 55%).",
    reasoning: null,
    confidence: 0.3,
    confidence_basis: null,
    produced_by: "astronomical_dating",
    engine: "starcode-astronomy/1.0",
    algorithm_reference: null,
    quoted_text: null,
    text_span_start: null,
    text_span_end: null,
    ordering: 0,
    references: [],
    locked: false,
    payload: {
      year: -584,
      month: 5,
      day: 28,
      hour_ut: null,
      gregorian_label: "28 May 585 BCE",
      fit: 0.55,
      anchor: "eclipse",
      recurrences: 0,
      engine: "starcode-astronomy/1.0",
      uncertainty_note: "ΔT uncertainty of tens of minutes applies to this date.",
      notes: ["A note about precession."],
      matched_criteria: [
        {
          criterion: "eclipse",
          matched: true,
          strength: 1,
          searchable: true,
          detail: "Total solar eclipse on 28 May 585 BCE.",
          evidence: {},
        },
      ],
      unmatched_criteria: [
        {
          criterion: "conjunction",
          matched: false,
          strength: 0,
          searchable: true,
          detail: "Jupiter and Saturn were not within 3° of each other near this date.",
          evidence: {},
        },
        {
          criterion: "unusual_darkness",
          matched: false,
          strength: 0,
          searchable: false,
          detail: "No astronomical mechanism produces multi-day darkness.",
          evidence: {},
        },
      ],
    } as unknown as Record<string, unknown>,
    ...overrides,
  } as Claim;
}

describe("DatingCandidates", () => {
  it("renders nothing when there are no candidates", () => {
    const { container } = render(<DatingCandidates claims={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the criteria a candidate failed alongside those it met", () => {
    render(<DatingCandidates claims={[candidate()]} />);

    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("Not matched")).toBeInTheDocument();
    expect(screen.getAllByText("Conjunction").length).toBeGreaterThan(0);
  });

  it("says why an unmatched criterion did not match", () => {
    render(<DatingCandidates claims={[candidate()]} />);
    expect(
      screen.getByText(/were not within 3° of each other/),
    ).toBeInTheDocument();
  });

  it("distinguishes a criterion that failed from one nothing can check", () => {
    /* Three days of darkness is not a failed match — no engine can decide it. Calling it
       a miss would imply a better date might satisfy it, which is untrue. */
    render(<DatingCandidates claims={[candidate()]} />);
    expect(screen.getByText(/not checkable/)).toBeInTheDocument();
  });

  it("expresses fit as a number and a label, not only as a bar", () => {
    render(<DatingCandidates claims={[candidate()]} />);

    expect(screen.getByText(/Fit 55%/)).toBeInTheDocument();
    expect(screen.getByText("1 of 3 criteria")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Fit 55 per cent/ }),
    ).toBeInTheDocument();
  });

  it("keeps the engine's uncertainty statement attached to the date", () => {
    render(<DatingCandidates claims={[candidate()]} />);
    expect(screen.getByText(/ΔT uncertainty/)).toBeInTheDocument();
  });

  it("names the framework behind a paid mode's candidate as a method, not a forecast", () => {
    const framed = candidate({
      payload: {
        ...(candidate().payload as Record<string, unknown>),
        framework: "Eschatological calculation",
      } as unknown as Record<string, unknown>,
    });
    render(<DatingCandidates claims={[framed]} />);

    const note = screen.getByText(/Produced by Eschatological calculation/);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toMatch(/not a prediction/);
  });

  it("renders a withheld candidate as a row rather than dropping it", () => {
    /* Locking is not deletion: the claim keeps its place so a reader can see that
       something is being withheld rather than a shorter list that looks complete. */
    const locked = candidate({
      locked: true,
      statement: "[Unlock with a paid plan to see this interpretation]",
    });
    render(<DatingCandidates claims={[locked]} />);

    const item = screen.getByRole("listitem");
    expect(within(item).getByText(/Unlock with a paid plan/)).toBeInTheDocument();
  });

  it("ranks the candidates in the order it was given", () => {
    const second = candidate({
      id: "claim-2",
      payload: {
        ...(candidate().payload as Record<string, unknown>),
        gregorian_label: "3 October 7 BCE",
      } as unknown as Record<string, unknown>,
    });
    const { container } = render(<DatingCandidates claims={[candidate(), second]} />);

    // Scoped to the ranked list itself: the expanded detail panel carries its own
    // <ul> of notes, so a document-wide listitem query would count those too.
    const ranked = container.querySelector("ol")!;
    const items = Array.from(ranked.children);
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("28 May 585 BCE");
    expect(items[1]?.textContent).toContain("3 October 7 BCE");
  });
});
