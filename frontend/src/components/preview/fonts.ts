import { Cormorant_Garamond, Rubik, Syne } from "next/font/google";

// Syne: expressive, wide display face for the preview's headlines.
export const syne = Syne({ subsets: ["latin"], weight: ["400", "500", "700", "800"] });

// Cormorant Garamond: the main site's original title face (same configuration as the cover page).
export const cormorant = Cormorant_Garamond({ subsets: ["latin"], weight: ["300", "500"] });

// Rubik: body text, matching the existing site and sector experiences.
export const rubik = Rubik({ subsets: ["latin"], weight: ["300", "400", "500"] });
