import StatusBanner from "../StatusBanner";
import { UiState } from "../../types";

type Props = {
  state: UiState;
  message: string;
  details?: string;
  hasApiResult: boolean;
  apiBase: string;
  apiOutput: string;
  onApiBaseChange: (value: string) => void;
  onSave: () => void;
  onHealth: () => void;
  onStatus: () => void;
};

export default function ApiCard(props: Props) {
  return (
    <section id="apiCard" className="card reveal" data-state={props.state}>
      <h2>API Verbindung</h2>
      <StatusBanner state={props.state} message={props.message} details={props.details} />
      {!props.hasApiResult ? (
        <div className="empty-state">
          <div className="empty-state-title">Noch kein API-Check</div>
          <div>Prüfe kurz, ob dein Backend erreichbar ist.</div>
          <div className="empty-actions">
            <button className="chip" onClick={props.onHealth}>
              Health prüfen
            </button>
          </div>
        </div>
      ) : null}

      <div className="row">
        <label htmlFor="apiBase">Base URL</label>
        <input id="apiBase" value={props.apiBase} onChange={(e) => props.onApiBaseChange(e.target.value)} />
        <button className="btn btn-secondary" onClick={props.onSave}>
          Speichern
        </button>
        <button className="btn" onClick={props.onHealth}>
          Health
        </button>
        <button className="btn" onClick={props.onStatus}>
          Status
        </button>
      </div>
      <pre className="output">{props.apiOutput}</pre>
    </section>
  );
}
