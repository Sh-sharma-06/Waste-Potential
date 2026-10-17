import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Waste-Potential | Process Simulator",
  description:
    "Explore waste-to-energy processes through an interactive 3D simulation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
