import type { CSSProperties } from "react";

/** Page background shared by the Industry hub and every page after it (simulator, marketplaces). */
export const INDUSTRY_PAGE_BG: CSSProperties = {
  backgroundImage: `
    linear-gradient(
      135deg,
      rgba(255, 248, 242, 0.45),
      rgba(245, 220, 205, 0.55)
    ),
    url('/industry-bg(new).jpg')
  `,
  backgroundSize: "cover",
  backgroundPosition: "center",
  backgroundAttachment: "fixed",
  backgroundRepeat: "no-repeat",
};
