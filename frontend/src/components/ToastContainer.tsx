import { Toast } from "../types";

export default function ToastContainer({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toast-root" aria-live="polite">
      {toasts.map((toast) => (
        <div className={`toast toast-${toast.type}`} key={toast.id}>
          <span className="toast-icon">{toast.type === "success" ? "✓" : toast.type === "warning" ? "⚠" : "!"}</span>
          <div className="toast-copy">
            <div className="toast-title">{toast.title}</div>
            {toast.details ? <div className="toast-details">{toast.details}</div> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
