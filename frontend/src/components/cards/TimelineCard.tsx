import StatusBanner from "../StatusBanner";
import { TimelineItem, UiState } from "../../types";

type Props = {
  state: UiState;
  message: string;
  details?: string;
  timelineItems: TimelineItem[];
  timelineInput: string;
  timelineSearch: string;
  timelineCategory: string;
  timelineCategories: string[];
  timelineGrouped: [string, TimelineItem[]][];
  onInputChange: (value: string) => void;
  onExtract: () => void;
  onSearchChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  normalizeCategory: (category: string) => string;
};

export default function TimelineCard(props: Props) {
  return (
    <section id="timelineCard" className="card reveal" data-state={props.state}>
      <h2>Timeline Extraktion</h2>
      <StatusBanner state={props.state} message={props.message} details={props.details} />
      {props.timelineItems.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">Kein Timeline-Ergebnis</div>
          <div>Füge Dokumenttext ein und starte die Extraktion.</div>
        </div>
      ) : null}
      <div className="col">
        <textarea
          rows={8}
          placeholder="Dokumenttext einfügen..."
          value={props.timelineInput}
          onChange={(e) => props.onInputChange(e.target.value)}
        />
        <button className="btn" onClick={props.onExtract}>
          Timeline extrahieren
        </button>
      </div>
      <div className="timeline-tools">
        <input
          type="text"
          placeholder="Suche in Titel/Beschreibung..."
          value={props.timelineSearch}
          onChange={(e) => props.onSearchChange(e.target.value)}
        />
        <select value={props.timelineCategory} onChange={(e) => props.onCategoryChange(e.target.value)}>
          <option value="">Alle Kategorien</option>
          {props.timelineCategories.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>
      <div className="timeline-list">
        {props.timelineItems.length === 0 ? (
          <div className="timeline-empty">
            <span className="empty-state-title">Noch keine Timeline</span>
            <br />
            Text eingeben und Extraktion starten.
          </div>
        ) : props.timelineGrouped.length === 0 ? (
          <div className="timeline-empty">Keine Einträge für den aktuellen Filter.</div>
        ) : (
          props.timelineGrouped.map(([dateIso, items]) => (
            <section className="timeline-group" key={dateIso}>
              <div className="timeline-group-date">{new Date(dateIso).toLocaleDateString("de-DE")}</div>
              <div className="timeline-cards">
                {items.map((item, idx) => (
                  <article className="timeline-card" key={`${dateIso}-${idx}-${item.title}`}>
                    <div className="timeline-card-head">
                      <div className="timeline-title">{item.title || "Ohne Titel"}</div>
                      <span className={`badge badge-${props.normalizeCategory(item.category || "info")}`}>
                        {props.normalizeCategory(item.category || "info")}
                      </span>
                    </div>
                    <div className="timeline-meta">
                      <span>Datum: {item.date_iso || "-"}</span>
                      {item.time_24h ? <span>Zeit: {item.time_24h}</span> : null}
                      {typeof item.amount_eur === "number" ? (
                        <span>
                          Betrag: {new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(item.amount_eur)}
                        </span>
                      ) : null}
                    </div>
                    <div className="timeline-desc">{item.description || ""}</div>
                  </article>
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </section>
  );
}
