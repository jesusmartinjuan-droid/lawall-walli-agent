import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchAgentImagePreview } from "../api/agent-images";
import { simulateDraft } from "../api/processing";
import { getErrorMessage } from "../utils/getErrorMessage";

const EXAMPLE_EMAIL =
  "Buenos días,\n\nQueríamos saber si tenéis disponibilidad para un pedido de revestimientos " +
  "para un local comercial, y si nos podéis pasar precios orientativos.\n\nGracias, un saludo.";

// Must match `IMAGE_PLACEHOLDER` in backend/app/services/email_provider_service.py —
// the literal marker the model places in the draft text at the point where
// the image should appear, so it doesn't always land at the very end.
const IMAGE_PLACEHOLDER = "[[IMAGEN]]";

function TextBlock({ text }: { text: string }) {
  if (!text) return null;
  return (
    <p style={{ margin: 0 }}>
      {text.split("\n").map((line, index, lines) => (
        <span key={index}>
          {line}
          {index < lines.length - 1 && <br />}
        </span>
      ))}
    </p>
  );
}

// Mirrors the exact structure `_build_reply_bodies` puts in the real HTML
// email — the reply text split around the image marker (if the model placed
// one), with the image rendered at that same point, so what staff see here
// is what the customer would actually see, not an approximation.
function EmailBodyPreview({
  generatedBody,
  imageId,
  imageName,
}: {
  generatedBody: string;
  imageId: number | null;
  imageName: string | null;
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (imageId === null) {
      setPreviewUrl(null);
      return;
    }
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

  const hasMarker = generatedBody.includes(IMAGE_PLACEHOLDER);
  const [before, after] = hasMarker
    ? generatedBody.split(IMAGE_PLACEHOLDER).map((part) => part.trim())
    : [generatedBody, ""];

  const imageBlock = imageId !== null && (
    <p style={{ margin: "12px 0" }}>
      {previewUrl ? (
        <img src={previewUrl} alt={imageName ?? ""} style={{ maxWidth: "100%" }} />
      ) : (
        <span className="page-subtitle">Cargando imagen…</span>
      )}
    </p>
  );

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: 8,
        padding: 20,
        background: "var(--color-surface)",
      }}
    >
      <TextBlock text={before} />
      {hasMarker ? (
        <>
          {imageBlock}
          <TextBlock text={after} />
        </>
      ) : (
        imageBlock
      )}
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
              <EmailBodyPreview
                generatedBody={simulateMutation.data.generated_body}
                imageId={simulateMutation.data.attached_image_id}
                imageName={simulateMutation.data.attached_image_name}
              />
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: "0 0 8px" }}>De dónde ha sacado esta respuesta</h4>
                {simulateMutation.data.sources_used.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {simulateMutation.data.sources_used.map((citation, index) => (
                      <div
                        key={index}
                        style={{
                          borderLeft: "3px solid var(--color-border)",
                          paddingLeft: 10,
                        }}
                      >
                        <span className="badge tone-neutral">{citation.source}</span>
                        <p style={{ fontStyle: "italic", margin: "4px 0 0" }}>“{citation.excerpt}”</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="page-subtitle" style={{ margin: 0 }}>
                    El agente no citó ninguna fuente concreta para esta respuesta.
                  </p>
                )}
              </div>
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
