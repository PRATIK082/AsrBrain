"use client";
import type { Answerability, AnswerabilityStatus } from "../../lib/types";

/**
 * The user-facing answer contract (docs/architecture/adr/0001).
 *
 * A numeric confidence is NOT a correctness rate and is never shown as one.
 * The four statuses below are computed from evidence, not from the model.
 */
const STATUS_CLASS: Record<AnswerabilityStatus, string> = {
  VERIFIED: "status-verified",
  EVIDENCE_SUPPORTED: "status-supported",
  NEEDS_ENGINEER_REVIEW: "status-review",
  INSUFFICIENT_EVIDENCE: "status-insufficient",
};

const STATUS_HINT: Record<AnswerabilityStatus, string> = {
  VERIFIED: "A deterministic tool result and the cited source evidence agree.",
  EVIDENCE_SUPPORTED: "The cited sources support this answer; no deterministic validation applies.",
  NEEDS_ENGINEER_REVIEW: "Partial, ambiguous or conflicting evidence — a human must review this.",
  INSUFFICIENT_EVIDENCE: "The indexed artifacts do not cover this question. Nothing is asserted.",
};

export function statusClass(status: AnswerabilityStatus): string {
  return STATUS_CLASS[status] ?? "status-review";
}

export function statusHint(status: AnswerabilityStatus): string {
  return STATUS_HINT[status] ?? "";
}

/** The status shown when the answerability gate has not been computed yet. */
export const UNCOMPUTED: Answerability = {
  status: "NEEDS_ENGINEER_REVIEW",
  reason: "Answerability gate not computed yet (Phase 5) — treat this answer as unverified.",
  missing: ["computed answerability status"],
  conflicts: [],
  checked: [],
};

export function StatusBadge({
  status,
  reason,
  className = "",
}: {
  status: AnswerabilityStatus;
  reason?: string;
  className?: string;
}) {
  return (
    <span
      className={`${statusClass(status)} ${className}`}
      title={reason || statusHint(status)}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
