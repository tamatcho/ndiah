import type { RefObject } from "react";
import StatusBanner from "../StatusBanner";
import { ChatMessage, Source, UiState } from "../../types";

type Props = {
  state: UiState;
  message: string;
  details?: string;
  chatHistory: ChatMessage[];
  chatQuestion: string;
  chatPending: boolean;
  exampleQuestions: string[];
  onQuestionChange: (value: string) => void;
  onAsk: () => void;
  onUseExample: (q: string) => void;
  onLoadSnippet: (messageId: string, source: Source) => void;
  historyRef: RefObject<HTMLDivElement>;
};

export default function ChatCard(props: Props) {
  return (
    <section id="chatCard" className="card reveal" data-state={props.state}>
      <h2>Chat über Dokumente</h2>
      <StatusBanner state={props.state} message={props.message} details={props.details} />
      <div id="chatHistory" className="chat-history" ref={props.historyRef}>
        {props.chatHistory.length === 0 ? (
          <div className="chat-empty">
            <div className="empty-state-title">Noch keine Nachrichten</div>
            <div>Starte mit einer Beispiel-Frage:</div>
            <div className="empty-actions">
              {props.exampleQuestions.map((q) => (
                <button key={q} className="chip" onClick={() => props.onUseExample(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          props.chatHistory.map((msg) => (
            <div className={`bubble ${msg.role === "user" ? "bubble-user" : "bubble-assistant"}`} key={msg.id}>
              <div className="bubble-role">{msg.role === "user" ? "Du" : "Assistant"}</div>
              <div className="bubble-text">{msg.text}</div>
              {msg.role === "assistant" && msg.sources && msg.sources.length > 0 ? (
                <details className="sources">
                  <summary>Sources ({msg.sources.length})</summary>
                  <ul className="sources-list">
                    {msg.sources.map((s) => {
                      const key = `${s.document_id}:${s.chunk_id}`;
                      return (
                        <li className="source-row" key={`${msg.id}-${key}`}>
                          <div>
                            document_id: {s.document_id}, chunk_id: {s.chunk_id}, score: {typeof s.score === "number" ? s.score.toFixed(3) : "-"}
                          </div>
                          <button className="source-btn" onClick={() => props.onLoadSnippet(msg.id, s)}>
                            Snippet laden
                          </button>
                          {msg.sourceDetails?.[key] ? <div className="source-snippet">{msg.sourceDetails[key]}</div> : null}
                        </li>
                      );
                    })}
                  </ul>
                </details>
              ) : null}
            </div>
          ))
        )}
      </div>
      <div className="col">
        <textarea
          rows={3}
          placeholder="z.B. Welche Zahlungen sind 2026 fällig?"
          value={props.chatQuestion}
          onChange={(e) => props.onQuestionChange(e.target.value)}
        />
        <button className="btn" disabled={props.chatPending} onClick={props.onAsk}>
          {props.chatPending ? "Frage läuft..." : "Frage senden"}
        </button>
      </div>
    </section>
  );
}
