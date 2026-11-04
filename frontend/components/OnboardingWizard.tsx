"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Step = 1 | 2 | 3;

export function OnboardingWizard() {
  const [step, setStep] = useState<Step>(1);
  const [context, setContext] = useState<any>(null);

  useEffect(() => {
    api.context().then(setContext).catch(() => setContext(null));
  }, []);

  if (!context) return null;
  if ((context?.data?.counts?.documents ?? 0) > 0) return null;

  return (
    <div className="rounded border border-[#00F5FF]/40 bg-[#0B0F17] p-4 text-sm">
      <h3 className="mb-2 font-mono text-[#00F5FF]">Getting started</h3>
      <div className="mb-3 text-xs text-[#A0A0A0]">Step {step} of 3</div>
      {step === 1 && (
        <div>
          <p className="mb-2">Add your first document or ARXML file.</p>
          <p className="text-xs text-[#A0A0A0]">Use the Knowledge tab or POST /ingest.</p>
        </div>
      )}
      {step === 2 && (
        <div>
          <p className="mb-2">Choose a model provider.</p>
          <p className="text-xs text-[#A0A0A0]">
            Ollama: {context?.models?.ollama?.status ?? "unknown"}
          </p>
        </div>
      )}
      {step === 3 && (
        <div>
          <p className="mb-2">Ask your first question in chat.</p>
          <p className="text-xs text-[#A0A0A0]">Try: “What is the Eth module?”</p>
        </div>
      )}
      <div className="mt-3 flex gap-2">
        {step > 1 && (
          <button className="rounded border border-[#1F2937] px-2 py-1" onClick={() => setStep((s) => (s - 1) as Step)}>
            Back
          </button>
        )}
        {step < 3 && (
          <button className="rounded border border-[#00F5FF] px-2 py-1 text-[#00F5FF]" onClick={() => setStep((s) => (s + 1) as Step)}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}