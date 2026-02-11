import { useEffect, useMemo, useState } from "react";
import StatusBanner from "../StatusBanner";
import { TimelineItem, UiState } from "../../types";

type Props = {
  state: UiState;
  message: string;
  details?: string;
  hasDocuments: boolean;
  timelineItems: TimelineItem[];
  timelineInput: string;
  timelineSearch: string;
  timelineCategory: string;
  timelineCategories: string[];
  timelineGrouped: [string, TimelineItem[]][];
  onInputChange: (value: string) => void;
  onExtract: () => void;
  onExtractDocuments: () => void;
  onSearchChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  normalizeCategory: (category: string) => string;
};

export default function TimelineCard(props: Props) {
  const [activeGroupIndex, setActiveGroupIndex] = useState(0);
  const [autoRotate, setAutoRotate] = useState(true);
  const [animationTick, setAnimationTick] = useState(0);
  const hasTimelineGroups = props.timelineGrouped.length > 0;
  const hasManyGroups = props.timelineGrouped.length > 1;

  const activeGroup = useMemo(() => {
    if (!hasTimelineGroups) return null;
    const safeIndex = Math.min(activeGroupIndex, props.timelineGrouped.length - 1);
    return props.timelineGrouped[safeIndex];
  }, [activeGroupIndex, hasTimelineGroups, props.timelineGrouped]);

  const formatGroupDate = (dateIso: string) => {
    const date = new Date(dateIso);
    if (Number.isNaN(date.getTime())) return dateIso;
    return date.toLocaleDateString("de-DE");
  };

  const goOlder = () => {
    if (!hasManyGroups) return;
    setActiveGroupIndex((prev) => (prev <= 0 ? props.timelineGrouped.length - 1 : prev - 1));
    setAnimationTick((v) => v + 1);
  };

  const goNewer = () => {
    if (!hasManyGroups) return;
    setActiveGroupIndex((prev) => (prev >= props.timelineGrouped.length - 1 ? 0 : prev + 1));
    setAnimationTick((v) => v + 1);
  };

  useEffect(() => {
    if (!hasTimelineGroups) {
      setActiveGroupIndex(0);
      return;
    }
    // Start with newest date first.
    setActiveGroupIndex(props.timelineGrouped.length - 1);
    setAutoRotate(true);
    setAnimationTick((v) => v + 1);
  }, [hasTimelineGroups, props.timelineGrouped]);

  useEffect(() => {
    if (!autoRotate || !hasManyGroups) return;
    const timer = window.setInterval(() => {
      setActiveGroupIndex((prev) => (prev <= 0 ? props.timelineGrouped.length - 1 : prev - 1));
      setAnimationTick((v) => v + 1);
    }, 4500);
    return () => window.clearInterval(timer);
  }, [autoRotate, hasManyGroups, props.timelineGrouped.length]);

  return (
    <section id="timelineCard" className="card reveal" data-state={props.state}>
      <h2>Timeline Extraktion</h2>
      <StatusBanner state={props.state} message={props.message} details={props.details} />
      {props.timelineItems.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">Kein Timeline-Ergebnis</div>
          <div>Füge Dokumenttext ein oder extrahiere direkt aus allen hochgeladenen Dokumenten.</div>
        </div>
      ) : null}
      <div className="col">
        <textarea
          rows={8}
          placeholder="Dokumenttext einfügen..."
          value={props.timelineInput}
          onChange={(e) => props.onInputChange(e.target.value)}
        />
        <div className="row wrap">
          <button className="btn" onClick={props.onExtract}>
            Aus Rohtext extrahieren
          </button>
          <button className="btn btn-secondary" onClick={props.onExtractDocuments} disabled={!props.hasDocuments}>
            Aus allen Dokumenten extrahieren
          </button>
        </div>
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
          <>
            <div className="timeline-carousel">
              <div className="timeline-counter">
                Gruppe {Math.min(activeGroupIndex + 1, props.timelineGrouped.length)} / {props.timelineGrouped.length}
              </div>
              <div className="timeline-nav">
                <button className="chip" onClick={goOlder} disabled={!hasManyGroups}>
                  Älter
                </button>
                <button className="chip" onClick={goNewer} disabled={!hasManyGroups}>
                  Neuer
                </button>
                <button className="chip" onClick={() => setAutoRotate((v) => !v)} disabled={!hasManyGroups}>
                  {autoRotate ? "Rotation pausieren" : "Rotation starten"}
                </button>
              </div>
            </div>

            {activeGroup ? (
              <section className="timeline-group timeline-group-animated" key={`${activeGroup[0]}-${animationTick}`}>
                <div className="timeline-group-date">
                  {formatGroupDate(activeGroup[0])}
                  {autoRotate && hasManyGroups ? <span className="timeline-rotate-badge">animiert</span> : null}
                </div>
                <div className="timeline-cards">
                  {activeGroup[1].map((item, idx) => (
                    <article className="timeline-card" key={`${activeGroup[0]}-${idx}-${item.title}`}>
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
                            Betrag:{" "}
                            {new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(item.amount_eur)}
                          </span>
                        ) : null}
                      </div>
                      <div className="timeline-desc">{item.description || ""}</div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
