export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-ES", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
