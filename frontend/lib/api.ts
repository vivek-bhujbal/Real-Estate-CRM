export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type Organization = { id: string; name: string; slug: string };
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  branch_id: string | null;
  department_id: string | null;
  is_active: boolean;
  created_at: string;
  organization: Organization;
  permissions: string[];
};

export type Session = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: CurrentUser;
};

export type MessageResponse = { message: string };

type ApiErrorBody = { error?: { code?: string; message?: string; request_id?: string } };
type SessionListener = (session: Session | null) => void;
type RequestOptions = { authenticated?: boolean; retryAuthentication?: boolean };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly requestId?: string
  ) {
    super(message);
  }
}

let activeSession: Session | null = null;
let refreshPromise: Promise<Session> | null = null;
const sessionListeners = new Set<SessionListener>();

export function setApiSession(session: Session | null): void {
  activeSession = session;
  for (const listener of sessionListeners) listener(session);
}

export function subscribeToApiSession(listener: SessionListener): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

export async function refreshSession(): Promise<Session> {
  if (!refreshPromise) {
    refreshPromise = requestOnce<Session>("/auth/refresh", { method: "POST" })
      .then((session) => {
        setApiSession(session);
        return session;
      })
      .catch((reason: unknown) => {
        setApiSession(null);
        throw reason;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {}
): Promise<T> {
  const authenticated = options.authenticated ?? true;
  const retryAuthentication = options.retryAuthentication ?? true;
  const headers = new Headers(init.headers);
  if (authenticated && activeSession) {
    headers.set("Authorization", `Bearer ${activeSession.access_token}`);
  }

  try {
    return await requestOnce<T>(path, { ...init, headers });
  } catch (reason) {
    const canRefresh =
      reason instanceof ApiError &&
      reason.status === 401 &&
      authenticated &&
      retryAuthentication &&
      activeSession !== null &&
      path !== "/auth/refresh";
    if (!canRefresh) throw reason;

    const restored = await refreshSession();
    headers.set("Authorization", `Bearer ${restored.access_token}`);
    return requestOnce<T>(path, { ...init, headers });
  }
}

async function requestOnce<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Invalid/non-JSON upstream responses use a safe generic message.
    }
    throw new ApiError(
      body.error?.message ?? "The request could not be completed",
      response.status,
      body.error?.code,
      body.error?.request_id
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
