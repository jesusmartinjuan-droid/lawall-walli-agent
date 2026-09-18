import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchAgentImagePreview } from "../api/agent-images";
import { simulateDraft } from "../api/processing";
import { getErrorMessage } from "../utils/getErrorMessage";

const EXAMPLE_EMAIL =
  "Buenos días,\n\nQueríamos saber si tenéis disponibilidad para un pedido de revestimientos " +
  "para un local comercial, y si nos podéis pasar precios orientativos.\n\nGracias, un saludo.";

function AttachedImagePreview({ imageId, name }: { imageId: number; name: string }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchAgentImagePreview(imageId).then((url) => {
      if (cancelled) {
        if (url) URL.revokeObjectURL(url);
        return;
      }
      objectUrl = url;
      setPreviewUrl(url);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageId]);

  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ margin: "0 0 8px" }}>Imagen que se incrustaría en el correo</h4>
      <div
        style={{
          border: "1px solid var(--color-border)",
          borderRadius: 8,
          padding: 8,
          display: "inline-block",
        }}
      >
        {previewUrl ? (
          <img src={previewUrl} alt={name} style={{ maxWidth: "100%", maxHeight: 240, display: "block" }} />
        ) : (
          <p className="page-subtitle" style={{ margin: 0 }}>
            Cargando vista previa…
          </p>
        )}
      </div>
      <p className="page-subtitle" style={{ marginTop: 4 }}>
        {name}
      </p>
    </div>
  );
}

export default function SimulatorPage() {
  const [emailBody, setEmailBody] = useState("");

  const simulateMutation = useMutation({
    mutationFn: simulateDraft,
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    simulateMutation.mutate(emailBody);
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Simulador</h1>
          <p className="page-subtitle">
            Escribe un correo de cliente de ejemplo y comprueba qué borrador generaría el agente
            ahora mismo, con el prompt y el conocimiento activos. No se envía ni se guarda nada —
            es solo una prueba.
          </p>
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "start" }}
      >
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Correo del cliente (simulado)</h3>
          <textarea
            value={emailBody}
            onChange={(e) => setEmailBody(e.target.value)}
            placeholder={EXAMPLE_EMAIL}
            style={{ width: "100%", minHeight: 280 }}
            required
          />
          <div className="btn-row" style={{ marginTop: 12 }}>
            <button type="submit" className="btn btn-primary" disabled={simulateMutation.isPending}>
              {simulateMutation.isPending ? "Generando…" : "Generar borrador"}
            </button>
          </div>
          {simulateMutation.isError && (
            <p className="error-text">
              {getErrorMessage(simulateMutation.error, "No se pudo generar el borrador de prueba.")}
            </p>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Borrador generado</h3>
          {simulateMutation.data ? (
            <>
              <pre className="detail-content">{simulateMutation.data.generated_body}</pre>
              {simulateMutation.data.attached_image_id !== null && (
                <AttachedImagePreview
                  imageId={simulateMutation.data.attached_image_id}
                  name={simulateMutation.data.attached_image_name ?? ""}
                />
              )}
            </>
          ) : (
            <p className="page-subtitle">
              {simulateMutation.isPending
                ? "Generando el borrador…"
                : "Escribe un correo a la izquierda y pulsa \"Generar borrador\"."}
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
