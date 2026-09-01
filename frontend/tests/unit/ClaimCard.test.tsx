import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClaimCard } from "@/components/ClaimCard";
import type { Claim } from "@/lib/types";

function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    id: "claim-1",
    section: "historical_context",
    claim_type: "ai_hypothesis",
    statement: "This may refer to a lunar eclipse.",
    reasoning: "Eclipse imagery is present but no date is given.",
    confidence: 0.3,
    confidence_basis: "Co-occurrence only.",
    produced_by: "astronomy",
    ordering: 0,
    payload: {},
    references: [],
    ...overrides,
  };
}

describe("ClaimCard", () => {
  it("always shows the claim type label", () => {
    render(<ClaimCard claim={makeClaim()} />);
    expect(screen.getByText("AI hypothesis")).toBeInTheDocument();
  });

  it("marks non-evidence claims as such", () => {
    render(<ClaimCard claim={makeClaim()} />);
    expect(screen.getByText("not evidence")).toBeInTheDocument();
  });

  it("does not mark evidence claims as non-evidence", () => {
    render(
      <ClaimCard
        claim={makeClaim({
          claim_type: "astronomical_calculation",
          engine: "starcode-astronomy/1.0",
          confidence: 0.9,
        })}
      />,
    );
    expect(screen.queryByText("not evidence")).not.toBeInTheDocument();
  });

  it("survives a claim whose references array is absent", () => {
    // Claims embedded in a stored report arrive without this field; a missing array
    // must render an empty section, never crash the report.
    const claim = makeClaim();
    delete (claim as { references?: unknown }).references;
    expect(() => render(<ClaimCard claim={claim} />)).not.toThrow();
    expect(screen.getByText("AI hypothesis")).toBeInTheDocument();
  });

  it("reveals reasoning and provenance on request", async () => {
    const user = userEvent.setup();
    render(
      <ClaimCard
        claim={makeClaim({
          claim_type: "astronomical_calculation",
          engine: "starcode-astronomy/1.0",
          algorithm_reference: "Meeus ch. 54",
          confidence: 0.9,
        })}
      />,
    );

    expect(screen.queryByText("Meeus ch. 54")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /why this/i }));
    expect(screen.getByText("Meeus ch. 54")).toBeInTheDocument();
    expect(screen.getByText("starcode-astronomy/1.0")).toBeInTheDocument();
  });

  it("flags a model-supplied citation as unverified", async () => {
    const user = userEvent.setup();
    render(
      <ClaimCard
        claim={makeClaim({
          references: [
            {
              id: "ref-1",
              citation_text: "Some Book (2019)",
              authors: [],
              reference_kind: "secondary",
              verified: false,
            },
          ],
        })}
      />,
    );
    await user.click(screen.getByRole("button", { name: /why this/i }));
    expect(screen.getByText(/unverified: check before citing/i)).toBeInTheDocument();
  });

  it("does not flag a corpus-verified citation", async () => {
    const user = userEvent.setup();
    render(
      <ClaimCard
        claim={makeClaim({
          references: [
            {
              id: "ref-1",
              citation_text: "Herodotus, Histories 1.74",
              authors: [],
              reference_kind: "primary",
              verified: true,
            },
          ],
        })}
      />,
    );
    await user.click(screen.getByRole("button", { name: /why this/i }));
    expect(screen.queryByText(/unverified/i)).not.toBeInTheDocument();
  });

  it("quotes source text verbatim in a blockquote", () => {
    render(
      <ClaimCard
        claim={makeClaim({
          claim_type: "source_text",
          statement: "The submitted text, recorded verbatim.",
          quoted_text: "and the moon became as blood",
          confidence: 1,
        })}
      />,
    );
    expect(screen.getByText("and the moon became as blood")).toBeInTheDocument();
  });

  it("describes confidence to assistive technology, not just colour", () => {
    render(<ClaimCard claim={makeClaim({ confidence: 0.3 })} />);
    expect(
      screen.getByRole("img", { name: /confidence 30 percent, low/i }),
    ).toBeInTheDocument();
  });
});
