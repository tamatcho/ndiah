export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, options);
  const raw = await resp.text();
  let body: any = { raw };
  try {
    body = raw ? JSON.parse(raw) : {};
  } catch {
    // ignore
  }
  if (!resp.ok) {
    throw new Error(body.detail || body.error || body.raw || `HTTP ${resp.status}`);
  }
  return body as T;
}

export function uploadWithProgress(
  baseUrl: string,
  file: File,
  onProgress: (loaded: number, total: number) => void
) {
  return new Promise<any>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl}/documents/upload`);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      onProgress(event.loaded, event.total);
    };

    xhr.onerror = () => reject(new Error("Netzwerkfehler beim Upload."));
    xhr.onload = () => {
      let data: any = {};
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch {
        // ignore
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(data.detail || `HTTP ${xhr.status}`));
        return;
      }
      resolve(data);
    };

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
