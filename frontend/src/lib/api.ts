export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface AuthUser {
  id: string;
  email: string;
  is_active: boolean;
  status?: string;
  email_verified_at?: string | null;
}

export interface CandidateProfileSummary {
  id: string;
  full_name: string;
  professional_headline: string | null;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Kept exclusively in memory; never persisted in localStorage or sessionStorage.
let inMemoryCsrfToken: string | null = null;
let inFlightCsrfPromise: Promise<string> | null = null;

export function clearInMemoryCsrfToken(): void {
  inMemoryCsrfToken = null;
  // Keep any in-flight request so concurrent retries share the same rotated
  // token instead of racing and invalidating each other.
}

async function ensureCsrfToken(): Promise<string> {
  if (inMemoryCsrfToken) {
    return inMemoryCsrfToken;
  }
  if (inFlightCsrfPromise) {
    return inFlightCsrfPromise;
  }
  inFlightCsrfPromise = (async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/csrf`, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new ApiError(response.status, "Unable to obtain CSRF token");
    }
    const data = (await response.json()) as { csrf_token: string };
    inMemoryCsrfToken = data.csrf_token;
    return data.csrf_token;
  })();
  try {
    return await inFlightCsrfPromise;
  } finally {
    inFlightCsrfPromise = null;
  }
}

const PUBLIC_AUTH_MUTATIONS = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/verify-email",
  "/api/v1/auth/resend-verification",
]);

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  _csrfRetried = false,
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const isStateChanging = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const isPublicAuthMutation = PUBLIC_AUTH_MUTATIONS.has(path);
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (isStateChanging && !isPublicAuthMutation) {
    const csrfToken = await ensureCsrfToken();
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    method,
    headers,
    credentials: "include",
  });

  if (response.status === 401) {
    clearInMemoryCsrfToken();
  }

  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // ignore non-JSON error bodies
    }
    if (
      response.status === 403 &&
      detail === "CSRF validation failed" &&
      isStateChanging &&
      !isPublicAuthMutation &&
      !_csrfRetried
    ) {
      clearInMemoryCsrfToken();
      return apiRequest<T>(path, options, true);
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function loginRequest(
  email: string,
  password: string,
): Promise<AuthUser> {
  const data = await apiRequest<{ user: AuthUser; csrf_token: string }>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
  );
  inMemoryCsrfToken = data.csrf_token;
  return data.user;
}

export async function logoutRequest(): Promise<void> {
  try {
    await apiRequest<void>("/api/v1/auth/logout", { method: "POST" });
  } finally {
    clearInMemoryCsrfToken();
  }
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>("/api/v1/auth/me", { method: "GET" });
}

export async function fetchOwnedProfiles(): Promise<CandidateProfileSummary[]> {
  return apiRequest<CandidateProfileSummary[]>("/api/v1/profiles", {
    method: "GET",
  });
}

export async function registerRequest(
  email: string,
  password: string,
): Promise<{ detail: string }> {
  return apiRequest<{ detail: string }>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function verifyEmailRequest(
  token: string,
): Promise<{ detail: string }> {
  return apiRequest<{ detail: string }>("/api/v1/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendVerificationRequest(
  email: string,
): Promise<{ detail: string }> {
  return apiRequest<{ detail: string }>("/api/v1/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}
