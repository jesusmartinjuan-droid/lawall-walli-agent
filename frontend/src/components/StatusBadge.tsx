const STATUS_LABELS: Record<string, string> = {
  received: "Recibido",
  processing: "Procesando",
  draft_generated: "Borrador generado",
  draft_created_in_mailbox: "Borrador creado en buzón",
  failed: "Fallido",
  ignored: "Ignorado",
  generated: "Generado",
  created_in_mailbox: "Creado en buzón",
  failed_to_create_in_mailbox: "No se pudo crear en buzón",
  discarded: "Descartado",
  pending: "Pendiente",
  success: "Correcto",
  retrying: "Reintentando",
};

const STATUS_TONES: Record<string, string> = {
  received: "tone-neutral",
  processing: "tone-info",
  draft_generated: "tone-info",
  draft_created_in_mailbox: "tone-success",
  failed: "tone-danger",
  failed_to_create_in_mailbox: "tone-warning",
  ignored: "tone-neutral",
  generated: "tone-info",
  created_in_mailbox: "tone-success",
  discarded: "tone-neutral",
  pending: "tone-neutral",
  success: "tone-success",
  retrying: "tone-warning",
};

export default function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? status;
  const tone = STATUS_TONES[status] ?? "tone-neutral";
  return <span className={`badge ${tone}`}>{label}</span>;
}
