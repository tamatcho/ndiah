import { useEffect, useRef, useState } from "react";
import StatusBanner from "../StatusBanner";
import { DocumentItem, DocumentStatus, UiState } from "../../types";

type Props = {
  disabled?: boolean;
  state: UiState;
  message: string;
  details?: string;
  selectedFilesCount: number;
  uploadErrors: string[];
  uploadPending: boolean;
  progressVisible: boolean;
  progressPercent: number;
  progressText: string;
  uploadOutput: string;
  documents: DocumentItem[];
  documentStatuses: Record<number, DocumentStatus>;
  onFiles: (files: File[]) => void;
  onUpload: () => void;
  onRetry: () => void;
  onDeleteAllDocuments: () => void;
  onDeleteDocument: (doc: DocumentItem) => void;
  onReprocessDocument: (doc: DocumentItem) => void;
  actionsPending: boolean;
};

export default function UploadCard(props: Props) {
  const dropRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [expandedDocId, setExpandedDocId] = useState<number | null>(null);
  const statusLabel = (status: DocumentStatus) => {
    if (status === "indexed") return "Verarbeitet";
    if (status === "processing") return "In Bearbeitung";
    return "Fehler";
  };

  useEffect(() => {
    if (props.selectedFilesCount === 0 && fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [props.selectedFilesCount]);

  return (
    <section id="uploadCard" className="card reveal" data-state={props.state}>
      <div className="card-title-row">
        <h2>PDF/ZIP Upload</h2>
        {props.state === "loading" ? <span className="card-title-spinner" aria-hidden="true" /> : null}
      </div>
      <div className="upload-panel-scroll">
        <StatusBanner state={props.state} message={props.message} details={props.details} />
        {props.selectedFilesCount === 0 ? (
          <div className="empty-state">
            <div className="empty-state-title">Keine Datei ausgewählt</div>
            <div>Ziehe PDFs/ZIPs hierher oder klicke auf Dateiauswahl.</div>
          </div>
        ) : null}

        <div
          ref={dropRef}
          className="dropzone"
          onDragOver={(e) => {
            e.preventDefault();
            if (props.disabled) return;
            dropRef.current?.classList.add("drag-over");
          }}
          onDragLeave={() => dropRef.current?.classList.remove("drag-over")}
          onDrop={(e) => {
            e.preventDefault();
            dropRef.current?.classList.remove("drag-over");
            if (props.disabled) return;
            props.onFiles(Array.from(e.dataTransfer.files));
          }}
        >
          <p>Dateien hier ablegen oder auswählen</p>
          <small>PDF oder ZIP (mit PDFs), max. 20 MB pro Datei</small>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf,.zip,application/zip,application/x-zip-compressed"
            multiple
            disabled={props.uploadPending || props.disabled}
            onChange={(e) => props.onFiles(Array.from(e.target.files || []))}
          />
        </div>

        <div className="validation-list">
          {props.uploadErrors.map((err, i) => (
            <div className="validation-item" key={`${err}-${i}`}>
              {err}
            </div>
          ))}
        </div>

        <div className="row wrap">
          <button className="btn" disabled={props.uploadPending || props.disabled} onClick={props.onUpload}>
            {props.uploadPending ? "Lade hoch..." : "Ausgewählte hochladen"}
          </button>
          {props.documents.length > 0 ? (
            <button
              className="chip"
              disabled={props.actionsPending || props.uploadPending || props.disabled}
              onClick={props.onDeleteAllDocuments}
            >
              Alle löschen
            </button>
          ) : null}
          {props.state === "error" && props.selectedFilesCount > 0 ? (
            <button className="chip" disabled={props.uploadPending || props.disabled} onClick={props.onRetry}>
              Erneut versuchen
            </button>
          ) : null}
        </div>

        {props.progressVisible ? (
          <div className="progress-wrap">
            <div className="progress-track">
              <div className="progress-bar" style={{ width: `${props.progressPercent}%` }} />
            </div>
            <div className="progress-text">{props.progressText}</div>
          </div>
        ) : null}

        <pre className="output">{props.uploadOutput}</pre>

        <div className="docs-list-wrap">
          <h3>Hochgeladene Dokumente</h3>
          <div className="doc-caption">Diese Dokumente bilden die Grundlage für Fristen, Zahlungen und Antworten.</div>
          <div className="docs-list">
            {props.documents.length === 0 ? (
              <div className="docs-list-empty">
                <div className="empty-state-title">Noch keine Dokumente</div>
                <div>Lade eine PDF oder ein ZIP mit PDFs hoch, um Chat und Timeline mit Quellen zu nutzen.</div>
              </div>
            ) : (
              props.documents.map((doc) => (
                <div className={`doc-item ${expandedDocId === doc.document_id ? "is-expanded" : ""}`} key={`${doc.document_id}-${doc.filename}`}>
                  <div className="doc-row">
                    <div className="doc-leading" aria-hidden="true">
                      <span className="doc-icon">PDF</span>
                    </div>
                    <div className="doc-main">
                      <div className="doc-name" title={doc.filename}>
                        {doc.filename}
                        {doc.quality_score != null && doc.quality_score < 0.3 ? (
                          <span
                            className="doc-quality-warn"
                            title={`Niedrige PDF-Qualität (Score: ${doc.quality_score.toFixed(2)}). Möglicherweise hauptsächlich Bilder ohne erkannten Text.`}
                          >
                            ⚠ Niedrige Qualität
                          </span>
                        ) : null}
                      </div>
                      <div className="doc-time">Hochgeladen: {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString("de-DE") : "-"}</div>
                    </div>
                    <div
                      className={`doc-status-badge status-${props.documentStatuses[doc.document_id] || "indexed"}`}
                      title="Verarbeitungsstatus"
                    >
                      {statusLabel(props.documentStatuses[doc.document_id] || "indexed")}
                    </div>
                    <details className="doc-menu">
                      <summary aria-label={`Aktionen für ${doc.filename}`}>⋯</summary>
                      <div className="doc-menu-popover">
                        <button
                          className="doc-menu-item"
                          disabled={props.actionsPending || props.disabled}
                          onClick={() =>
                            setExpandedDocId((prev) => (prev === doc.document_id ? null : doc.document_id))
                          }
                        >
                          {expandedDocId === doc.document_id ? "Details ausblenden" : "Details"}
                        </button>
                        <button
                          className="doc-menu-item danger"
                          disabled={props.actionsPending || props.disabled}
                          onClick={() => props.onDeleteDocument(doc)}
                        >
                          Löschen
                        </button>
                      </div>
                    </details>
                  </div>
                  {expandedDocId === doc.document_id ? (
                    <div className="doc-details-panel">
                      <div className="doc-details-row">
                        <span className="doc-details-key">Dokument-ID</span>
                        <span>{doc.document_id}</span>
                      </div>
                      <div className="doc-details-row">
                        <span className="doc-details-key">Property-ID</span>
                        <span>{doc.property_id}</span>
                      </div>
                      <div className="doc-details-row">
                        <span className="doc-details-key">Hochgeladen</span>
                        <span>{doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString("de-DE") : "-"}</span>
                      </div>
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
