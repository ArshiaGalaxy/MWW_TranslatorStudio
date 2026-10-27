import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LanguageProvider, type Locale } from "@/lib/i18n";
import { ThemeProvider, ToastProvider } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Vira Studio — Persian Manga Translation",
  description:
    "Upload a manga chapter and automate detection, translation, cleanup and Persian typesetting — publish-ready pages in one studio.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#111522" },
    { media: "(prefers-color-scheme: light)", color: "#f7f4ea" },
  ],
};

// The bootstrap script only handles the theme: the locale is already correct
// in the server-rendered <html lang/dir> below (read from the cookie), and
// lib/i18n keeps that cookie in sync.
const bootstrap = `(function(){try{
var t=localStorage.getItem("vira.theme")||"light";
var r=document.documentElement;
r.classList.toggle("dark",t==="dark");
r.classList.toggle("light",t!=="dark");
}catch(e){}})();`;

function readLocaleCookie(locale: string | undefined): Locale {
  return locale === "fa" ? "fa" : "en";
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const locale = readLocaleCookie(cookieStore.get("vira.locale")?.value);

  return (
    <html
      lang={locale}
      dir={locale === "fa" ? "rtl" : "ltr"}
      data-scroll-behavior="smooth"
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: bootstrap }} />
      </head>
      <body className="antialiased">
        <ThemeProvider>
          <LanguageProvider initialLocale={locale}>
            <ToastProvider>
              <AuthProvider>{children}</AuthProvider>
            </ToastProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
