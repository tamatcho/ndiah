import { UiState } from "../types";

export default function StatusBanner({
  state,
  message,
  details
}: {
  state: UiState;
  message: string;
  details?: string;
}) {
  const icon = state === "loading" ? "◔" : state === "success" ? "✓" : state === "error" ? "!" : "○";
  return (
    <div className="status-banner-wrap" data-state={state}>
      <div className="status-banner">
        <span className="status-icon" aria-hidden="true">
          {icon}
        </span>
        <div className="status-copy">
          <div className="status-message">{message}</div>
          {details ? <div className="status-details">{details}</div> : null}
        </div>
      </div>
    </div>
  );
}
