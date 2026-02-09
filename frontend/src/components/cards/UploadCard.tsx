import { useRef } from "react";
import StatusBanner from "../StatusBanner";
import { DocumentItem, UiState } from "../../types";

type Props = {
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
  onFiles: (files: File[]) => void;
  onUpload: () => void;
};

export default function UploadCard(props: Props) {
  const dropRef = useRef<HTMLDivElement | null>(null);

  return (
    <section id="uploadCard" className="card reveal" data-state={props.state}>
      <h2>PDF Upload</h2>
      <StatusBanner state={props.state} message={props.message} details={props.details} />
      {props.selectedFilesCount === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">Keine Datei ausgewählt</div>
          <div>Ziehe PDFs hierher oder klicke auf Dateiauswahl.</div>
        </div>
      ) : null}

      <div
        ref={dropRef}
        className="dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          dropRef.current?.classList.add("drag-over");
        }}
        onDragLeave={() => dropRef.current?.classList.remove("drag-over")}
        onDrop={(e) => {
          e.preventDefault();
          dropRef.current?.classList.remove("drag-over");
          props.onFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <p>Dateien hier ablegen oder auswählen</p>
        <small>PDF, max. 20 MB pro Datei</small>
        <input
          type="file"
          accept=".pdf,application/pdf"
          multiple
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
        <button className="btn" disabled={props.uploadPending} onClick={props.onUpload}>
          {props.uploadPending ? "Lade hoch..." : "Ausgewählte hochladen"}
        </button>
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
        <div className="docs-list">
          {props.documents.length === 0 ? (
            <div className="docs-list-empty">
              <div className="empty-state-title">Noch keine Dokumente</div>
              <div>Lade eine PDF hoch, um Chat und Timeline mit Quellen zu nutzen.</div>
            </div>
          ) : (
            props.documents.map((doc) => (
              <div className="doc-item" key={`${doc.document_id}-${doc.filename}`}>
                <div className="doc-name" title={doc.filename}>
                  {doc.filename}
                </div>
                <div className="doc-time">{doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString("de-DE") : "-"}</div>
                <div className="doc-id">ID {doc.document_id}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
