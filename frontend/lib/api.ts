"use client";

/** API client with session cookies + CSRF handling. */

function getCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { json?: unknown } = {},
): Promise<T> {
  // Routes are registered without trailing slashes (the dev proxy strips
  // them anyway); normalizing keeps direct-backend usage consistent too.
  const normalized =
    path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
  const { json, ...rest } = options;
  const headers: Record<string, string> = {
    ...(rest.headers as Record<string, string>),
  };
  if (json !== undefined) headers["Content-Type"] = "application/json";
  const method = (rest.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    const token = getCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }

  const res = await fetch(normalized, {
    ...rest,
    method,
    headers,
    credentials: "include",
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail =
        typeof data === "object" && data !== null
          ? Object.entries(data)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
              .join(" · ") || detail
          : String(data);
    } catch {
      /* keep default */
    }
    throw new ApiError(res.status, detail);
  }
  // 204 No Content (e.g. DRF DELETE) has an empty body — nothing to parse.
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, json?: unknown) =>
    request<T>(path, { method: "POST", json }),
  patch: <T>(path: string, json?: unknown) =>
    request<T>(path, { method: "PATCH", json }),
  put: <T>(path: string, json?: unknown) =>
    request<T>(path, { method: "PUT", json }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),

  uploadForm: async <T>(path: string, form: FormData): Promise<T> => {
    const token = getCookie("csrftoken");
    const normalized =
      path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
    const res = await fetch(normalized, {
      method: "POST",
      credentials: "include",
      headers: {
        ...(token ? { "X-CSRFToken": token } : {}),
      },
      body: form,
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      const text = await res.text();
      try {
        const data = JSON.parse(text);
        detail =
          typeof data === "object" && data !== null
            ? Object.entries(data)
                .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
                .join(" · ") || detail
            : String(data);
      } catch {
        if (text) detail = `${detail} — ${text.slice(0, 300)}`;
      }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<T>;
  },
};
