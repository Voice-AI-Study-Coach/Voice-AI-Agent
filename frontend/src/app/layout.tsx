import type { Metadata } from "next";
import { Inter, Lora } from "next/font/google";
import { ThemeProvider, themeScript } from "@/components/theme-provider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Questions and headings are set in a serif: it slows reading slightly, which
// is the right feel for material you are meant to think about rather than skim.
const lora = Lora({
  subsets: ["latin"],
  variable: "--font-lora",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Study Coach",
  description: "Turn your notes into a spoken quiz that adapts as you answer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${lora.variable}`}
      // The inline script sets data-theme before paint, so the server HTML and
      // the first client render legitimately differ on this attribute.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
