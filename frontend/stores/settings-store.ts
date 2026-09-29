import { create } from "zustand";

interface SettingsState {
  provider: "ollama" | "openai_compat";
  model: string;
  apiKey: string;
  set: (p: Partial<SettingsState>) => void;
}

export const useSettings = create<SettingsState>((set) => ({
  provider: "ollama",
  model: "",
  apiKey: "",
  set: (p) => set(p),
}));
