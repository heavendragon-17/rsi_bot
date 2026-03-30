/**
 * Base API client.
 * All HTTP calls and SSE connections go through these utilities.
 */

const BASE_URL = (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------

/**
 * Typed fetch wrapper. Throws ApiError on non-2xx responses.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json() as { detail?: string; error?: string };
      message = body.detail ?? body.error ?? message;
    } catch {
      // ignore parse error, keep default message
    }
    throw new ApiError(res.status, message);
  }

  // 204 No Content — return empty object cast to T
  if (res.status === 204) return {} as T;

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// apiSSE
// ---------------------------------------------------------------------------

/**
 * Open an SSE connection to `path`.
 *
 * @param path     - API path (relative, e.g. "/api/backtest/1/progress")
 * @param onMessage - called with (eventName, parsedData) for each event
 * @param onError  - called on connection error (optional)
 * @returns cleanup function — call it to close the EventSource
 */
export function apiSSE(
  path: string,
  onMessage: (event: string, data: unknown) => void,
  onError?: (err: Event) => void,
  maxRetries: number = 3,
): () => void {
  let es: EventSource | null = null;
  let retryCount = 0;
  let isClosed = false;

  const connect = () => {
    if (isClosed) return;
    es = new EventSource(`${BASE_URL}${path}`);

    // Generic message handler (handles unnamed `data:` lines)
    es.onmessage = (e: MessageEvent) => {
      try {
        onMessage("message", JSON.parse(e.data as string));
      } catch {
        onMessage("message", e.data);
      }
    };

    // Named event types from SSE spec
    for (const eventName of ["progress", "complete", "error", "download_progress", "download_complete"]) {
      es.addEventListener(eventName, (e: Event) => {
        const me = e as MessageEvent;
        try {
          onMessage(eventName, JSON.parse(me.data as string));
        } catch {
          onMessage(eventName, me.data);
        }
      });
    }

    es.onerror = (e) => {
      if (isClosed) return;
      es?.close();
      if (retryCount < maxRetries) {
        retryCount++;
        setTimeout(connect, 1000 * retryCount);
      } else {
        onError?.(e);
      }
    };

    es.onopen = () => {
      retryCount = 0;
    };
  };

  connect();

  return () => {
    isClosed = true;
    es?.close();
  };
}
