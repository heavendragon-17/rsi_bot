/**
 * Base API client.
 * All HTTP calls and SSE connections go through these utilities.
 */

// In production builds the UI is served by FastAPI at the same origin, so an
// empty BASE_URL (relative URLs) is correct. In dev (`npm run dev`) Vite runs
// on a different port, so default to the API's dev port.
const _env = (import.meta as { env?: { VITE_API_URL?: string; PROD?: boolean } }).env ?? {};
const BASE_URL = _env.VITE_API_URL ?? (_env.PROD ? "" : "http://localhost:8100");

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

async function apiErrorFromResponse(res: Response, path: string): Promise<ApiError> {
  let message = `HTTP ${res.status}`;
  try {
    const body = await res.json() as { detail?: string; error?: string; type?: string };
    message = body.detail ?? body.error ?? message;
    console.error(`[API] ${res.status} ${path}:`, body);
  } catch {
    console.error(`[API] ${res.status} ${path}: (no JSON body)`);
  }
  return new ApiError(res.status, message);
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
  console.log(`[API] ${options?.method ?? "GET"} ${path}`);

  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
  } catch (networkErr) {
    console.error(`[API] Network error on ${path}:`, networkErr);
    throw networkErr;
  }

  if (!res.ok) {
    throw await apiErrorFromResponse(res, path);
  }

  // 204 No Content — return empty object cast to T
  if (res.status === 204) return {} as T;

  console.log(`[API] ${res.status} ${path} OK`);
  return res.json() as Promise<T>;
}

export interface ApiDownload {
  blob: Blob;
  filename: string | null;
}

function responseFilename(res: Response): string | null {
  const disposition = res.headers.get("Content-Disposition");
  if (!disposition) return null;
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return encoded;
    }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? null;
}

export async function apiDownload(path: string): Promise<ApiDownload> {
  const url = `${BASE_URL}${path}`;
  console.log(`[API] GET ${path}`);
  const res = await fetch(url);
  if (!res.ok) throw await apiErrorFromResponse(res, path);
  return { blob: await res.blob(), filename: responseFilename(res) };
}

export async function apiBinaryUpload<T>(path: string, body: Blob): Promise<T> {
  const url = `${BASE_URL}${path}`;
  console.log(`[API] POST ${path}`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": body.type || "application/zip" },
    body,
  });
  if (!res.ok) throw await apiErrorFromResponse(res, path);
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
    console.log(`[SSE] Connecting to ${path}`);
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
        console.log(`[SSE] Event: ${eventName}`, me.data);
        try {
          onMessage(eventName, JSON.parse(me.data as string));
        } catch {
          onMessage(eventName, me.data);
        }
      });
    }

    es.onerror = (e) => {
      if (isClosed) return;
      console.warn(`[SSE] Connection error (retry ${retryCount + 1}/${maxRetries})`, e);
      es?.close();
      if (retryCount < maxRetries) {
        retryCount++;
        setTimeout(connect, 1000 * retryCount);
      } else {
        console.error(`[SSE] Max retries reached, giving up`);
        onError?.(e);
      }
    };

    es.onopen = () => {
      console.log(`[SSE] Connected to ${path}`);
      retryCount = 0;
    };
  };

  connect();

  return () => {
    isClosed = true;
    es?.close();
  };
}
