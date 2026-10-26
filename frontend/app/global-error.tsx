"use client";

/**
 * Last-resort boundary — replaces the whole document, so it cannot rely on
 * the root layout, providers, or i18n. Keep it dependency-free and bilingual
 * inline.
 */

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          background: "#090b11",
          color: "#e9edf8",
          fontFamily: "system-ui, sans-serif",
          textAlign: "center",
          padding: 24,
        }}
      >
        <h1 style={{ fontSize: 22, margin: 0 }}>Something went wrong · مشکلی پیش آمد</h1>
        <p style={{ color: "#96a0bd", maxWidth: 420, margin: 0 }}>
          An unexpected error occurred. · خطای غیرمنتظره‌ای رخ داد.
        </p>
        <button
          onClick={reset}
          style={{
            background: "#6d7cff",
            color: "#fff",
            border: "none",
            borderRadius: 10,
            padding: "10px 22px",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Try again · تلاش دوباره
        </button>
        {/* Keep the digest visible for support/debugging */}
        {error.digest && (
          <code style={{ color: "#5e6885", fontSize: 11 }}>{error.digest}</code>
        )}
      </body>
    </html>
  );
}
