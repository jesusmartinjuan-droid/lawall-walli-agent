import { useMutation } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";

import { simulateDraft } from "../api/processing";
import { getErrorMessage } from "../utils/getErrorMessage";

const EXAMPLE_EMAIL =
  "Buenos días,\n\nQueríamos saber si tenéis disponibilidad para un pedido de revestimientos " +
  "para un local comercial, y si nos podéis pasar precios orientativos.\n\nGracias, un saludo.";

// The model writes real Markdown (bold, lists, and occasionally an inline
// ![alt](url) image it found via web_search on la-wall.com) — this renders
// it for real instead of showing the literal syntax, matching exactly what
// the real email's HTML body does (see email_provider_service.py). Single
// newlines stay as line breaks (remarkBreaks), matching that same nl2br
// behavior, so the preview layout matches the real email.
function RenderedBody({ text }: { text: string }) {
  if (!text) return null;
  return (
    <ReactMarkdown
      remarkPlugins={[remarkBreaks]}
      components={{
        img: ({ src, alt }) => (
          <img src={src} alt={alt} style={{ maxWidth: "100%", margin: "12px 0", borderRadius: 4 }} />
        ),
        p: ({ children }) => <p style={{ margin: "0 0 8px" }}>{children}</p>,
      }}
    >
      {text}
    </ReactMarkdown>
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
            ahora mismo, con el prompt y los archivos activos. No se envía ni se guarda nada —
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
              <div
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  padding: 20,
                  background: "var(--color-surface)",
                }}
              >
                <RenderedBody text={simulateMutation.data.generated_body} />
                {simulateMutation.data.generated_images.map((image, index) => (
                  <img
                    key={index}
                    src={`data:${image.content_type};base64,${image.data_base64}`}
                    alt={image.filename}
                    style={{ maxWidth: "100%", marginTop: 12, borderRadius: 4 }}
                  />
                ))}
              </div>
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: "0 0 8px" }}>De dónde ha sacado esta respuesta</h4>
                {simulateMutation.data.sources_used.length > 0 ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {simulateMutation.data.sources_used.map((name) => (
                      <span key={name} className="badge tone-neutral">
                        {name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="page-subtitle" style={{ margin: 0 }}>
                    El agente no consultó ningún archivo concreto para esta respuesta.
                  </p>
                )}
              </div>
            </>
          ) : simulateMutation.isPending ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </span>
              <p className="page-subtitle" style={{ margin: 0 }}>
                Generando el borrador…
              </p>
            </div>
          ) : (
            <p className="page-subtitle">
              Escribe un correo a la izquierda y pulsa "Generar borrador".
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
