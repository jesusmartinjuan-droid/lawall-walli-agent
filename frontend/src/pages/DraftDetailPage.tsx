import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getProcessingDetail } from "../api/processing";
import StatusBadge from "../components/StatusBadge";
import { formatDateTime } from "../utils/formatDate";

export default function DraftDetailPage() {
  const { emailMessageId } = useParams<{ emailMessageId: string }>();
  const id = Number(emailMessageId);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["processing", id],
    queryFn: () => getProcessingDetail(id),
    enabled: Number.isFinite(id),
  });

  return (
    <div>
      <Link to="/drafts" className="back-link">
        ← Volver al historial
      </Link>

      {isLoading && <p>Cargando…</p>}
      {isError && <p className="error-text">No se pudo cargar el detalle del procesamiento.</p>}

      {data && (
        <>
          <div className="page-header">
            <div>
              <h1>{data.subject}</h1>
              <p className="page-subtitle">
                De {data.sender} · Recibido el {formatDateTime(data.received_at)}
              </p>
            </div>
            <StatusBadge status={data.final_status} />
          </div>

          <details className="detail-section" open>
            <summary>Correo original</summary>
            <pre className="detail-content">{data.body_text ?? data.body_html ?? "(sin contenido)"}</pre>
          </details>

          <details className="detail-section">
            <summary>Historial del hilo usado como contexto</summary>
            <pre className="detail-content">{data.thread_context ?? "(sin historial)"}</pre>
          </details>

          <details className="detail-section">
            <summary>Documentos incluidos en el contexto</summary>
            {data.documents_used.length === 0 ? (
              <p className="page-subtitle">No se incluyeron documentos.</p>
            ) : (
              <ul>
                {data.documents_used.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            )}
          </details>

          <details className="detail-section">
            <summary>Sitios web incluidos en el contexto</summary>
            {data.web_sources_used.length === 0 ? (
              <p className="page-subtitle">No se incluyó ninguna web.</p>
            ) : (
              <ul>
                {data.web_sources_used.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            )}
          </details>

          {data.prompt_content_snapshot && (
            <details className="detail-section">
              <summary>Prompt utilizado</summary>
              <pre className="detail-content">{data.prompt_content_snapshot}</pre>
            </details>
          )}

          <details className="detail-section" open>
            <summary>Borrador generado</summary>
            {data.generated_body ? (
              <>
                <pre className="detail-content">{data.generated_body}</pre>
                {data.draft_status && (
                  <p className="page-subtitle" style={{ marginTop: 8 }}>
                    Estado del borrador: <StatusBadge status={data.draft_status} />
                  </p>
                )}
              </>
            ) : (
              <p className="page-subtitle">Todavía no se ha generado ningún borrador.</p>
            )}
          </details>

          <details className="detail-section">
            <summary>Registro de procesamiento (reintentos: {data.retry_count})</summary>
            {data.logs.length === 0 ? (
              <p className="page-subtitle">Sin registros todavía.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Paso</th>
                    <th>Estado</th>
                    <th>Error</th>
                    <th>Inicio</th>
                    <th>Fin</th>
                  </tr>
                </thead>
                <tbody>
                  {data.logs.map((log) => (
                    <tr key={log.id}>
                      <td>{log.step}</td>
                      <td>
                        <StatusBadge status={log.status} />
                      </td>
                      <td>{log.error_message ?? "—"}</td>
                      <td>{formatDateTime(log.started_at)}</td>
                      <td>{formatDateTime(log.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </details>
        </>
      )}
    </div>
  );
}
