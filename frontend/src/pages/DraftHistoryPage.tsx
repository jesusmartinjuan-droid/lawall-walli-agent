import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { listProcessing } from "../api/processing";
import StatusBadge from "../components/StatusBadge";
import { formatDateTime } from "../utils/formatDate";

export default function DraftHistoryPage() {
  const navigate = useNavigate();
  const { data: items, isLoading } = useQuery({ queryKey: ["processing"], queryFn: listProcessing });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Historial de borradores</h1>
          <p className="page-subtitle">Correos procesados por Walli y el estado de su borrador.</p>
        </div>
      </div>

      {isLoading && <p>Cargando…</p>}

      {items && items.length === 0 && <div className="empty-state">Todavía no se ha procesado ningún correo.</div>}

      {items && items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Buzón</th>
              <th>Asunto</th>
              <th>Remitente</th>
              <th>Recibido</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.email_message_id}
                className="clickable"
                onClick={() => navigate(`/drafts/${item.email_message_id}`)}
              >
                <td>{item.mailbox_name}</td>
                <td>{item.subject}</td>
                <td>{item.sender}</td>
                <td>{formatDateTime(item.received_at)}</td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
