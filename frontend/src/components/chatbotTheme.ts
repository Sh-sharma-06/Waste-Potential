/** Look and route matching for the FloatingChatbot, shown only on the Industry tab. */

export type ChatSector = "industry";

export interface ChatTheme {
  panelBg: string;
  panelBorder: string;
  panelShadow: string;
  text: string;
  muted: string;
  headerBg: string;
  headerText: string;
  headerLabel: string;
  controlBg: string;
  controlBorder: string;
  optionBg: string;
  optionText: string;
  userBubbleBg: string;
  userBubbleBorder: string;
  userLabel: string;
  botBubbleBg: string;
  botBubbleBorder: string;
  botLabel: string;
  bubbleShadow: string;
  chipBg: string;
  chipBorder: string;
  chipText: string;
  activeBg: string;
  activeBorder: string;
  activeText: string;
  statusBg: string;
  statusBorder: string;
  statusText: string;
  errorBg: string;
  errorBorder: string;
  errorText: string;
  divider: string;
  inputBarBg: string;
  inputBg: string;
  inputBorder: string;
  inputText: string;
  accentGradient: string;
  accentText: string;
  accentSolid: string;
  launcherShadow: string;
}

const LIGHT_SHARED = {
  headerText: "#FFFFFF",
  headerLabel: "rgba(255,255,255,0.85)",
  controlBg: "rgba(255,255,255,0.18)",
  controlBorder: "rgba(255,255,255,0.4)",
  bubbleShadow: "0 2px 10px rgba(0,0,0,0.06)",
  activeBg: "rgba(22,163,74,0.15)",
  activeBorder: "#16a34a",
  activeText: "#15803d",
  errorBg: "rgba(239,68,68,0.08)",
  errorBorder: "rgba(185,28,28,0.3)",
  errorText: "#b91c1c",
  inputBg: "#FFFFFF",
  accentText: "#FFFFFF",
};

/** Industry hub, simulator and marketplaces: light warm background, orange accent. */
const INDUSTRY: ChatTheme = {
  ...LIGHT_SHARED,
  panelBg: "rgba(255,250,245,0.97)",
  panelBorder: "rgba(194,65,12,0.4)",
  panelShadow: "0 20px 50px rgba(120,53,15,0.25)",
  text: "#27120A",
  muted: "#7A4A38",
  headerBg: "linear-gradient(90deg, #9A3412 0%, #C2410C 50%, #EA580C 100%)",
  optionBg: "#FFFFFF",
  optionText: "#27120A",
  userBubbleBg: "#FDE7D8",
  userBubbleBorder: "rgba(234,88,12,0.35)",
  userLabel: "#C2410C",
  botBubbleBg: "#FFFFFF",
  botBubbleBorder: "rgba(67,30,18,0.12)",
  botLabel: "#9A3412",
  chipBg: "rgba(194,65,12,0.08)",
  chipBorder: "rgba(194,65,12,0.3)",
  chipText: "#C2410C",
  statusBg: "rgba(234,88,12,0.08)",
  statusBorder: "rgba(234,88,12,0.4)",
  statusText: "#C2410C",
  divider: "rgba(194,65,12,0.15)",
  inputBarBg: "#FBF0E8",
  inputBorder: "rgba(194,65,12,0.25)",
  inputText: "#27120A",
  accentGradient: "linear-gradient(90deg, #C2410C 0%, #EA580C 100%)",
  accentSolid: "#C2410C",
  launcherShadow: "0 6px 24px rgba(194,65,12,0.45)",
};

export interface ChatRouteConfig {
  theme: ChatTheme;
  sector: ChatSector;
  placeholder: string;
  /** Distance from the viewport bottom, to clear fixed docks on some pages. */
  bottomOffset: number;
}

const startsWithAny = (path: string, prefixes: string[]) =>
  prefixes.some((p) => path === p || path.startsWith(`${p}/`));

/** Industry tab: hub, material breakdown, simulator and both marketplaces. */
const INDUSTRY_ROUTES = ["/explore/industry", "/simulator", "/market"];

/** Chatbot config for the current route, or null where the chatbot is hidden. */
export function chatConfigForPath(pathname: string | null): ChatRouteConfig | null {
  const path = pathname || "/";
  if (!startsWithAny(path, INDUSTRY_ROUTES)) return null;
  return {
    theme: INDUSTRY,
    sector: "industry",
    placeholder: "Ask about results, pathways, buyers...",
    // The energy marketplace has a fixed "Generate Audit Report" dock along the bottom.
    bottomOffset: startsWithAny(path, ["/market/energy"]) ? 104 : 24,
  };
}
