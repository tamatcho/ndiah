import { useEffect, useMemo, useRef, useState } from "react";
import ApiCard from "./components/cards/ApiCard";
import ChatCard from "./components/cards/ChatCard";
import TimelineCard from "./components/cards/TimelineCard";
import UploadCard from "./components/cards/UploadCard";
import ToastContainer from "./components/ToastContainer";
import { fetchJson, uploadWithProgress } from "./lib/api";
import { ApiStatus, ChatMessage, DocumentItem, Source, TimelineItem, Toast, UiState } from "./types";

const BASE_KEY = "property_ai_base_url";
const CHAT_HISTORY_KEY = "property_ai_chat_history";
const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const EXAMPLE_QUESTIONS = [
  "Welche Zahlungen sind 2026 fällig?",
  "Wann ist die nächste Eigentümerversammlung?",
  "Welche Fristen stehen bald an?"
];

function uuid() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeCategory(category: string) {
  return ["meeting", "payment", "deadline", "info"].includes(category) ? category : "info";
}

export default function App() {
  const [apiBase, setApiBase] = useState(
    () => (localStorage.getItem(BASE_KEY) || DEFAULT_API_BASE).replace(/\/+$/, "")
  );
  const [backendDown, setBackendDown] = useState(false);

  const [apiState, setApiState] = useState<UiState>("idle");
  const [apiMessage, setApiMessage] = useState("Bereit");
  const [apiDetails, setApiDetails] = useState("Base URL prüfen und Status abrufen.");
  const [hasApiResult, setHasApiResult] = useState(false);
  const [apiOutput, setApiOutput] = useState("");

  const [uploadState, setUploadState] = useState<UiState>("idle");
  const [uploadMessage, setUploadMessage] = useState("Bereit");
  const [uploadDetails, setUploadDetails] = useState("PDF auswählen und hochladen.");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [uploadOutput, setUploadOutput] = useState("");
  const [uploadPending, setUploadPending] = useState(false);
  const [progressVisible, setProgressVisible] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressText, setProgressText] = useState("0%");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  const [chatState, setChatState] = useState<UiState>("idle");
  const [chatMessage, setChatMessage] = useState("Bereit");
  const [chatDetails, setChatDetails] = useState("Frage zu indexierten Dokumenten stellen.");
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatPending, setChatPending] = useState(false);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>(() => {
    try {
      const raw = localStorage.getItem(CHAT_HISTORY_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });

  const [timelineState, setTimelineState] = useState<UiState>("idle");
  const [timelineMessage, setTimelineMessage] = useState("Bereit");
  const [timelineDetails, setTimelineDetails] = useState("Rohtext einfügen und Termine extrahieren.");
  const [timelineInput, setTimelineInput] = useState("");
  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [timelineSearch, setTimelineSearch] = useState("");
  const [timelineCategory, setTimelineCategory] = useState("");

  const [toasts, setToasts] = useState<Toast[]>([]);
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem(BASE_KEY, apiBase);
  }, [apiBase]);

  useEffect(() => {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
  }, [chatHistory]);

  useEffect(() => {
    if (!chatHistoryRef.current) return;
    chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
  }, [chatHistory]);

  const addToast = (type: Toast["type"], title: string, details?: string) => {
    const id = uuid();
    setToasts((prev) => [...prev, { id, type, title, details }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  };

  const loadDocuments = async () => {
    try {
      const docs = await fetchJson<DocumentItem[]>(`${apiBase}/documents`);
      setDocuments(Array.isArray(docs) ? docs : []);
    } catch {
      // no-op
    }
  };

  const initialHealthCheck = async () => {
    setApiState("loading");
    setApiMessage("Prüfe API beim Start...");
    setApiOutput("Lade...");
    try {
      const data = await fetchJson<{ ok: boolean }>(`${apiBase}/health`);
      setApiOutput(JSON.stringify(data, null, 2));
      setHasApiResult(true);
      setApiState("success");
      setApiMessage("API erreichbar");
      setApiDetails("Health OK.");
      setBackendDown(false);
    } catch {
      setApiOutput("Backend nicht erreichbar.");
      setApiState("error");
      setApiMessage("Backend nicht erreichbar");
      setApiDetails("Prüfe Server, URL und CORS.");
      setBackendDown(true);
    }
  };

  useEffect(() => {
    void initialHealthCheck();
    void loadDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runHealth = async () => {
    setApiState("loading");
    setApiMessage("Prüfe API Health...");
    setApiOutput("Lade...");
    try {
      const data = await fetchJson<{ ok: boolean }>(`${apiBase}/health`);
      setApiOutput(JSON.stringify(data, null, 2));
      setApiState("success");
      setApiMessage("API erreichbar");
      setApiDetails("Health OK.");
      setHasApiResult(true);
      setBackendDown(false);
      addToast("success", "Health erfolgreich");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      setApiOutput(`Fehler: ${message}`);
      setApiState("error");
      setApiMessage("API Fehler");
      setApiDetails(message);
      setBackendDown(true);
      addToast("error", "Health fehlgeschlagen", message);
    }
  };

  const runStatus = async () => {
    setApiState("loading");
    setApiMessage("Lade Dokument-Status...");
    setApiOutput("Lade...");
    try {
      const data = await fetchJson<ApiStatus>(`${apiBase}/documents/status`);
      setApiOutput(JSON.stringify(data, null, 2));
      setApiState("success");
      setApiMessage("Status geladen");
      setApiDetails("");
      setHasApiResult(true);
      addToast("success", "Status geladen");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      setApiOutput(`Fehler: ${message}`);
      setApiState("error");
      setApiMessage("Status fehlgeschlagen");
      setApiDetails(message);
      addToast("error", "Status fehlgeschlagen", message);
    }
  };

  const validateFiles = (files: File[]) => {
    const valid: File[] = [];
    const errors: string[] = [];
    for (const file of files) {
      const isPdfType = file.type === "application/pdf";
      const hasPdfExt = file.name.toLowerCase().endsWith(".pdf");
      if (!isPdfType && !hasPdfExt) {
        errors.push(`${file.name}: nur PDF-Dateien sind erlaubt.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name}: Datei ist größer als 20 MB.`);
        continue;
      }
      valid.push(file);
    }
    return { valid, errors };
  };

  const addFiles = (files: File[]) => {
    const { valid, errors } = validateFiles(files);
    setSelectedFiles((prev) => {
      const map = new Map(prev.map((f) => [`${f.name}:${f.size}`, f]));
      for (const file of valid) map.set(`${file.name}:${file.size}`, file);
      return Array.from(map.values());
    });
    setUploadErrors([...errors, ...(valid.length ? [`${valid.length} Datei(en) hinzugefügt.`] : [])]);
    if (errors.length > 0) {
      setUploadState("error");
      setUploadMessage("Ungültige Dateien erkannt");
      setUploadDetails(`${errors.length} Datei(en) abgelehnt.`);
    } else {
      setUploadState("idle");
      setUploadMessage("Bereit");
      setUploadDetails("PDF auswählen und hochladen.");
    }
  };

  const onUpload = async () => {
    if (!selectedFiles.length) {
      setUploadErrors(["Bitte mindestens eine gültige PDF auswählen."]);
      setUploadState("error");
      setUploadMessage("Keine Datei gewählt");
      addToast("error", "Upload fehlgeschlagen", "Bitte gültige PDF-Dateien wählen.");
      return;
    }

    setUploadPending(true);
    setUploadState("loading");
    setUploadMessage("Upload läuft...");
    setUploadDetails(`${selectedFiles.length} Datei(en)`);
    setUploadOutput("Upload läuft...");
    setProgressVisible(true);
    setProgressPercent(0);
    setProgressText("0%");

    let uploaded = 0;
    let failed = 0;
    const lines: string[] = [];

    for (let i = 0; i < selectedFiles.length; i += 1) {
      const file = selectedFiles[i];
      try {
        const data = await uploadWithProgress(apiBase, file, (loaded, total) => {
          const current = total ? loaded / total : 0;
          const overall = ((i + current) / selectedFiles.length) * 100;
          setProgressPercent(Math.max(0, Math.min(100, overall)));
          setProgressText(`${Math.round(overall)}% (${i + 1}/${selectedFiles.length}) ${file.name}`);
        });
        uploaded += 1;
        lines.push(`OK ${data.filename} (document_id: ${data.document_id}, indexed chunks: ${data.chunks_indexed})`);
      } catch (e) {
        failed += 1;
        const message = e instanceof Error ? e.message : "Fehler";
        lines.push(`FAIL ${file.name}: ${message}`);
      }
    }

    setUploadOutput(lines.join("\n"));
    setProgressPercent(100);
    setProgressText(`100% (${uploaded}/${selectedFiles.length}) abgeschlossen`);

    if (failed === 0) {
      setUploadState("success");
      setUploadMessage("Upload erfolgreich");
      setUploadDetails(`${uploaded} Datei(en) verarbeitet.`);
      addToast("success", "Upload erfolgreich", `${uploaded} Datei(en)`);
    } else if (uploaded > 0) {
      setUploadState("error");
      setUploadMessage("Teilweise fehlgeschlagen");
      setUploadDetails(`${uploaded} erfolgreich, ${failed} fehlgeschlagen.`);
      addToast("error", "Upload teilweise fehlgeschlagen", `${failed} Fehler`);
    } else {
      setUploadState("error");
      setUploadMessage("Upload fehlgeschlagen");
      setUploadDetails(`${failed} Fehler`);
      addToast("error", "Upload fehlgeschlagen", `${failed} Fehler`);
    }

    setUploadPending(false);
    setSelectedFiles([]);
    window.setTimeout(() => {
      setProgressVisible(false);
      setProgressPercent(0);
      setProgressText("0%");
    }, 600);
    await loadDocuments();
  };

  const askChat = async (question: string) => {
    if (!question.trim()) {
      setChatState("error");
      setChatMessage("Leere Frage");
      addToast("error", "Chat fehlgeschlagen", "Bitte Frage eingeben.");
      return;
    }

    const q = question.trim();
    setChatHistory((prev) => [...prev, { id: uuid(), role: "user", text: q }]);
    setChatQuestion("");
    setChatPending(true);
    setChatState("loading");
    setChatMessage("Frage läuft...");

    try {
      const data = await fetchJson<{ answer: string; sources: Source[] }>(`${apiBase}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q })
      });
      setChatHistory((prev) => [
        ...prev,
        { id: uuid(), role: "assistant", text: data.answer || "", sources: data.sources || [], sourceDetails: {} }
      ]);
      setChatState("success");
      setChatMessage("Antwort erhalten");
      setChatDetails(`${data.sources?.length || 0} Quellen im Kontext.`);
      addToast("success", "Chat erfolgreich", `${data.sources?.length || 0} Quellen`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      setChatHistory((prev) => [...prev, { id: uuid(), role: "assistant", text: `Fehler: ${message}` }]);
      setChatState("error");
      setChatMessage("Chat fehlgeschlagen");
      setChatDetails(message);
      addToast("error", "Chat fehlgeschlagen", message);
    } finally {
      setChatPending(false);
    }
  };

  const loadSourceSnippet = async (messageId: string, source: Source) => {
    try {
      const data = await fetchJson<{ snippet: string }>(
        `${apiBase}/documents/source?document_id=${encodeURIComponent(source.document_id)}&chunk_id=${encodeURIComponent(
          source.chunk_id
        )}`
      );
      setChatHistory((prev) =>
        prev.map((msg) => {
          if (msg.id !== messageId) return msg;
          const details = { ...(msg.sourceDetails || {}) };
          details[`${source.document_id}:${source.chunk_id}`] = data.snippet || "";
          return { ...msg, sourceDetails: details };
        })
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      addToast("error", "Snippet konnte nicht geladen werden", message);
    }
  };

  const extractTimeline = async () => {
    if (!timelineInput.trim()) {
      setTimelineState("error");
      setTimelineMessage("Kein Text");
      addToast("error", "Timeline fehlgeschlagen", "Bitte Text einfügen.");
      return;
    }
    setTimelineState("loading");
    setTimelineMessage("Extraktion läuft...");
    try {
      const data = await fetchJson<{ items: TimelineItem[] }>(`${apiBase}/timeline/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: timelineInput })
      });
      const items = Array.isArray(data.items) ? data.items : [];
      setTimelineItems(items);
      setTimelineState("success");
      setTimelineMessage("Timeline extrahiert");
      setTimelineDetails(`${items.length} Einträge gefunden.`);
      addToast("success", "Timeline extrahiert", `${items.length} Einträge`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      setTimelineState("error");
      setTimelineMessage("Extraktion fehlgeschlagen");
      setTimelineDetails(message);
      addToast("error", "Timeline fehlgeschlagen", message);
    }
  };

  const extractTimelineFromDocuments = async () => {
    if (documents.length === 0) {
      setTimelineState("error");
      setTimelineMessage("Keine Dokumente");
      setTimelineDetails("Bitte zuerst mindestens ein PDF hochladen.");
      addToast("error", "Timeline fehlgeschlagen", "Keine hochgeladenen Dokumente gefunden.");
      return;
    }

    setTimelineState("loading");
    setTimelineMessage("Extrahiere aus allen Dokumenten...");
    setTimelineDetails(`${documents.length} Dokument(e) ausgewählt.`);
    try {
      const data = await fetchJson<{
        items: TimelineItem[];
        documents_considered: number;
        documents_processed: number;
        documents_failed: Array<{ document_id: number; filename: string; reason: string }>;
      }>(`${apiBase}/timeline/extract-documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });

      const items = Array.isArray(data.items) ? data.items : [];
      const failed = Array.isArray(data.documents_failed) ? data.documents_failed.length : 0;
      setTimelineItems(items);
      setTimelineState("success");
      setTimelineMessage("Timeline aus Dokumenten extrahiert");
      setTimelineDetails(
        `${items.length} Einträge, ${data.documents_processed || 0}/${data.documents_considered || documents.length} Dokumente verarbeitet, ${failed} fehlgeschlagen.`
      );
      addToast("success", "Timeline extrahiert", `${items.length} Einträge aus Dokumenten`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unbekannter Fehler";
      setTimelineState("error");
      setTimelineMessage("Extraktion aus Dokumenten fehlgeschlagen");
      setTimelineDetails(message);
      addToast("error", "Timeline fehlgeschlagen", message);
    }
  };

  const filteredTimeline = useMemo(() => {
    const sorted = [...timelineItems].sort((a, b) => {
      const da = new Date(a.date_iso).getTime();
      const db = new Date(b.date_iso).getTime();
      if (da !== db) return da - db;
      return (a.time_24h || "99:99").localeCompare(b.time_24h || "99:99");
    });

    return sorted.filter((item) => {
      const category = normalizeCategory(item.category);
      if (timelineCategory && category !== timelineCategory) return false;
      const q = timelineSearch.trim().toLowerCase();
      if (!q) return true;
      return `${item.title || ""} ${item.description || ""}`.toLowerCase().includes(q);
    });
  }, [timelineItems, timelineCategory, timelineSearch]);

  const timelineCategories = useMemo(
    () => Array.from(new Set(timelineItems.map((x) => normalizeCategory(x.category || "info")))).sort(),
    [timelineItems]
  );

  const timelineGrouped = useMemo(() => {
    const map = new Map<string, TimelineItem[]>();
    for (const item of filteredTimeline) {
      const key = item.date_iso || "Unbekannt";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return Array.from(map.entries());
  }, [filteredTimeline]);

  const documentsById = useMemo(
    () =>
      Object.fromEntries(
        documents.map((doc) => [doc.document_id, doc] as const)
      ) as Record<number, DocumentItem>,
    [documents]
  );

  return (
    <>
      <div className="bg-orb orb-a" />
      <div className="bg-orb orb-b" />

      <main className="shell">
        <section id="backendAlert" className="backend-alert" hidden={!backendDown}>
          <div className="backend-alert-title">Backend nicht erreichbar</div>
          <div className="backend-alert-copy">
            Prüfe diese Punkte:
            <ul className="backend-alert-list">
              <li>Server läuft (`uvicorn app.main:app ...`)</li>
              <li>Base URL ist korrekt</li>
              <li>CORS ist aktiv</li>
            </ul>
          </div>
          <div className="empty-actions">
            <button className="btn" onClick={() => void runHealth()}>
              Erneut prüfen
            </button>
          </div>
        </section>

        <header className="hero reveal">
          <p className="eyebrow">Property AI</p>
          <h1>Dokumente verstehen. Fragen stellen. Fristen sehen.</h1>
          <p className="sub">Frontend für Upload, Retrieval-Chat und Timeline-Extraktion.</p>
        </header>

        <ApiCard
          state={apiState}
          message={apiMessage}
          details={apiDetails}
          hasApiResult={hasApiResult}
          apiBase={apiBase}
          apiOutput={apiOutput}
          onApiBaseChange={setApiBase}
          onSave={() => addToast("success", "Base URL gespeichert", apiBase)}
          onHealth={() => void runHealth()}
          onStatus={() => void runStatus()}
        />

        <UploadCard
          state={uploadState}
          message={uploadMessage}
          details={uploadDetails}
          selectedFilesCount={selectedFiles.length}
          uploadErrors={uploadErrors}
          uploadPending={uploadPending}
          progressVisible={progressVisible}
          progressPercent={progressPercent}
          progressText={progressText}
          uploadOutput={uploadOutput}
          documents={documents}
          onFiles={addFiles}
          onUpload={() => void onUpload()}
        />

        <ChatCard
          state={chatState}
          message={chatMessage}
          details={chatDetails}
          chatHistory={chatHistory}
          chatQuestion={chatQuestion}
          chatPending={chatPending}
          exampleQuestions={EXAMPLE_QUESTIONS}
          documentsById={documentsById}
          onQuestionChange={setChatQuestion}
          onAsk={() => void askChat(chatQuestion)}
          onUseExample={setChatQuestion}
          onLoadSnippet={(messageId, source) => void loadSourceSnippet(messageId, source)}
          historyRef={chatHistoryRef}
        />

        <TimelineCard
          state={timelineState}
          message={timelineMessage}
          details={timelineDetails}
          hasDocuments={documents.length > 0}
          timelineItems={timelineItems}
          timelineInput={timelineInput}
          timelineSearch={timelineSearch}
          timelineCategory={timelineCategory}
          timelineCategories={timelineCategories}
          timelineGrouped={timelineGrouped}
          onInputChange={setTimelineInput}
          onExtract={() => void extractTimeline()}
          onExtractDocuments={() => void extractTimelineFromDocuments()}
          onSearchChange={setTimelineSearch}
          onCategoryChange={setTimelineCategory}
          normalizeCategory={normalizeCategory}
        />
      </main>

      <ToastContainer toasts={toasts} />
    </>
  );
}
