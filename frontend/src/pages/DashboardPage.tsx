import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getDashboardSummary } from "../api/dashboard";
import StatusBadge from "../components/StatusBadge";
import { formatDateTime } from "../utils/formatDate";

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Resumen de la actividad de Walli.</p>
        </div>
      </div>

      {isLoading && <p>Cargando…</p>}
      {isError && <p className="error-text">No se pudo cargar el resumen.</p>}

      {data && (
        <>
          <div className="card-grid">
            <MetricCard label="Buzones activos" value={`${data.active_mailboxes} / ${data.total_mailboxes}`} />
            <MetricCard label="Documentos cargados" value={`${data.active_documents} / ${data.total_documents}`} />
            <MetricCard label="Prompts configurados" value={`${data.active_prompts} / ${data.total_prompts}`} />
            <MetricCard label="Correos procesados" value={data.processed_emails} />
            <MetricCard label="Borradores generados" value={data.generated_drafts} />
          </div>

          <h2>Últimos errores de procesamiento</h2>
          {data.recent_errors.length === 0 ? (
            <div className="empty-state">No hay errores recientes.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Buzón</th>
                  <th>Asunto</th>
                  <th>Remitente</th>
                  <th>Recibido</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.recent_errors.map((item) => (
                  <tr key={item.email_message_id}>
                    <td>{item.mailbox_name}</td>
                    <td>{item.subject}</td>
                    <td>{item.sender}</td>
                    <td>{formatDateTime(item.received_at)}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>
                      <Link to={`/drafts/${item.email_message_id}`}>Ver detalle</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}
