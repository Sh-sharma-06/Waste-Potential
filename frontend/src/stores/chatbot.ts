/**
 * Zustand store for the global floating chatbot.
 *
 * The chatbot is mounted once in the root layout; pages that have live data worth
 * grounding answers in (e.g. the simulator's results) publish it here.
 */

import { create } from "zustand";

interface ChatbotState {
  /** Page data sent to the assistant as context; null when the page publishes none. */
  context: Record<string, unknown> | null;
  setContext: (context: Record<string, unknown> | null) => void;
}

export const useChatbotStore = create<ChatbotState>((set) => ({
  context: null,
  setContext: (context) => set({ context }),
}));
