export class ApiError extends Error {
  status?: number;
  isTimeout: boolean;
  latencyMs?: number;

  constructor(message: string, opts: { status?: number; isTimeout?: boolean; latencyMs?: number } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = opts.status;
    this.isTimeout = Boolean(opts.isTimeout);
    this.latencyMs = opts.latencyMs;
  }
}

let authToken: string | null = null;

export function setApiAuthToken(token: string | null) {
  authToken = token;
}

type ApiFetchOptions = RequestInit & {
  timeoutMs?: number;
};

function parseResponse(raw: string) {
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return { raw };
  }
}

export function normalizeApiError(error: unknown, fallback = "Unbekannter Fehler") {
  if (error instanceof ApiError) {
    const rawMsg = error.message || fallback;
    const msg = /traceback|stack|exception|sqlalchemy|operationalerror/i.test(rawMsg)
      ? fallback
      : rawMsg;
    if (error.isTimeout) {
      return "Zeitüberschreitung. Bitte erneut versuchen.";
    }
    if (error.status === 401) {
      return "Sitzung abgelaufen. Bitte erneut einloggen.";
    }
    if (error.status === 413) {
      return msg || "Datei zu groß. Bitte eine kleinere PDF-Datei hochladen.";
    }
    if (error.status === 429) {
      return msg || "Limit erreicht. Bitte reduziere die Anzahl der Dokumente.";
    }
    if (!error.status) {
      return "Netzwerkfehler. Bitte Verbindung prüfen und erneut versuchen.";
    }
    if (msg.includes("Freikontingent erreicht")) {
      return msg;
    }
    return msg;
  }
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}

export async function apiFetch<T>(url: string, options: ApiFetchOptions = {}): Promise<{ data: T; latencyMs: number; status: number }> {
  const { timeoutMs = 30000, ...requestOptions } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = performance.now();
  const headers = new Headers(requestOptions.headers || undefined);
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  try {
    const resp = await fetch(url, {
      ...requestOptions,
      headers,
      credentials: requestOptions.credentials ?? "include",
      signal: requestOptions.signal || controller.signal
    });
    const raw = await resp.text();
    const body: any = parseResponse(raw);
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));

    if (!resp.ok) {
      throw new ApiError(body.message || body.detail || body.error || body.raw || `HTTP ${resp.status}`, {
        status: resp.status,
        latencyMs
      });
    }

    return {
      data: body as T,
      latencyMs,
      status: resp.status
    };
  } catch (error: any) {
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));
    if (error?.name === "AbortError") {
      throw new ApiError("Zeitüberschreitung der Anfrage. Bitte erneut versuchen.", { isTimeout: true, latencyMs });
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError(error?.message || "Netzwerkfehler", { latencyMs });
  } finally {
    window.clearTimeout(timer);
  }
}

export async function apiCall<T>(url: string, options: ApiFetchOptions = {}): Promise<{ data: T; latencyMs: number; status: number }> {
  return apiFetch<T>(url, options);
}

export async function fetchUploadJobStatus(apiBase: string, jobId: number) {
  const { data } = await apiFetch<import("../types").UploadJob>(`${apiBase}/documents/upload-jobs/${jobId}`);
  return data;
}

type ApiChatMessage = {
  id: number;
  role: string;
  text: string;
  sources: import("../types").Source[];
  created_at: string;
};

export async function fetchChatHistory(apiBase: string, propertyId: number | null): Promise<ApiChatMessage[]> {
  const url = propertyId != null
    ? `${apiBase}/chat/history?property_id=${propertyId}`
    : `${apiBase}/chat/history`;
  const { data } = await apiFetch<ApiChatMessage[]>(url);
  return data;
}

export async function deleteChatHistory(apiBase: string, propertyId: number | null): Promise<void> {
  const url = propertyId != null
    ? `${apiBase}/chat/history?property_id=${propertyId}`
    : `${apiBase}/chat/history`;
  await apiFetch(url, { method: "DELETE" });
}

export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const { data } = await apiFetch<T>(url, options);
  return data;
}

export function uploadWithProgress(
  baseUrl: string,
  propertyId: number,
  file: File,
  onProgress: (loaded: number, total: number) => void
) {
  return new Promise<any>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl}/documents/upload`);
    xhr.withCredentials = true;
    xhr.timeout = 180000;
    if (authToken) {
      xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
    }

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      onProgress(event.loaded, event.total);
    };

    xhr.onerror = () => reject(new ApiError("Netzwerkfehler beim Upload."));
    xhr.ontimeout = () => reject(new ApiError("Upload hat zu lange gedauert. Bitte erneut versuchen.", { isTimeout: true }));
    xhr.onload = () => {
      let data: any = {};
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch {
        // ignore
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(data.message || data.detail || `HTTP ${xhr.status}`, { status: xhr.status }));
        return;
      }
      resolve(data);
    };

    const form = new FormData();
    form.append("property_id", String(propertyId));
    form.append("file", file);
    xhr.send(form);
  });
}
