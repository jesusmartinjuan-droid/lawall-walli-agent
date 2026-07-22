import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { deleteDocument, listDocuments, uploadDocument } from "../api/documents";
import {
  activateWebSource,
  createWebSource,
  deactivateWebSource,
  deleteWebSource,
  listWebSources,
  refreshWebSource,
} from "../api/web-sources";
import type { WebSourceFormValues } from "../types";
import { formatDateTime } from "../utils/formatDate";

const ACCEPTED_EXTENSIONS = ".txt,.md,.pdf,.docx,.xlsx";

const EMPTY_WEB_SOURCE_FORM: WebSourceFormValues = {
  name: "",
  root_url: "",
  max_pages: 20,
};

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const { data: documents, isLoading } = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["documents"] });

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      invalidate();
      setUploadError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: () => setUploadError("No se pudo subir el documento. Formato no soportado o error de red."),
  });

  const deleteMutation = useMutation({ mutationFn: deleteDocument, onSuccess: invalidate });

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  }

  // --- Web sources ------------------------------------------------------
  const { data: webSources, isLoading: isLoadingWebSources } = useQuery({
    queryKey: ["web-sources"],
    queryFn: listWebSources,
  });
  const [showWebSourceForm, setShowWebSourceForm] = useState(false);
  const [webSourceForm, setWebSourceForm] = useState<WebSourceFormValues>(EMPTY_WEB_SOURCE_FORM);

  const invalidateWebSources = () => queryClient.invalidateQueries({ queryKey: ["web-sources"] });

  const createWebSourceMutation = useMutation({
    mutationFn: createWebSource,
    onSuccess: () => {
      invalidateWebSources();
      setShowWebSourceForm(false);
      setWebSourceForm(EMPTY_WEB_SOURCE_FORM);
    },
  });
  const deleteWebSourceMutation = useMutation({ mutationFn: deleteWebSource, onSuccess: invalidateWebSources });
  const activateWebSourceMutation = useMutation({
    mutationFn: activateWebSource,
    onSuccess: invalidateWebSources,
  });
  const deactivateWebSourceMutation = useMutation({
    mutationFn: deactivateWebSource,
    onSuccess: invalidateWebSources,
  });
  const refreshWebSourceMutation = useMutation({
    mutationFn: refreshWebSource,
    onSuccess: invalidateWebSources,
  });

  function handleWebSourceSubmit(event: FormEvent) {
    event.preventDefault();
    createWebSourceMutation.mutate(webSourceForm);
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Documentos</h1>
          <p className="page-subtitle">
            Sube documentos de conocimiento (.txt, .md, .pdf, .docx, .xlsx) para el contexto del
            agente.
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={handleFileChange}
            style={{ display: "none" }}
            id="document-upload-input"
          />
          <label htmlFor="document-upload-input" className="btn btn-primary" style={{ cursor: "pointer" }}>
            {uploadMutation.isPending ? "Subiendo…" : "Subir documento"}
          </label>
        </div>
      </div>

      {uploadError && <p className="error-text">{uploadError}</p>}
      {isLoading && <p>Cargando…</p>}

      {documents && documents.length === 0 && (
        <div className="empty-state">No hay documentos cargados todavía.</div>
      )}

      {documents && documents.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Archivo</th>
              <th>Texto extraído</th>
              <th>Estado</th>
              <th>Subido</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.original_filename}</td>
                <td>{doc.text_length.toLocaleString("es-ES")} caracteres</td>
                <td>
                  <span className={`badge ${doc.is_active ? "tone-success" : "tone-neutral"}`}>
                    {doc.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>{formatDateTime(doc.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    onClick={() => {
                      if (confirm(`¿Eliminar el documento "${doc.original_filename}"?`)) {
                        deleteMutation.mutate(doc.id);
                      }
                    }}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="page-header" style={{ marginTop: 40 }}>
        <div>
          <h2 style={{ marginTop: 0 }}>Sitios web</h2>
          <p className="page-subtitle">
            Añade la web de la empresa para que el agente también use su contenido como contexto. Se
            rastrean las páginas internas del mismo dominio y se actualizan periódicamente. También
            admite enlaces de Google Docs, siempre que el documento esté compartido como "cualquiera
            con el enlace puede ver": su contenido se mantiene sincronizado en cada actualización.
          </p>
        </div>
        {!showWebSourceForm && (
          <button type="button" className="btn btn-primary" onClick={() => setShowWebSourceForm(true)}>
            Nueva fuente web
          </button>
        )}
      </div>

      {showWebSourceForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleWebSourceSubmit}>
          <h3 style={{ marginTop: 0 }}>Nueva fuente web</h3>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="web-source-name">Nombre</label>
              <input
                id="web-source-name"
                type="text"
                value={webSourceForm.name}
                onChange={(e) => setWebSourceForm({ ...webSourceForm, name: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="web-source-url">URL raíz</label>
              <input
                id="web-source-url"
                type="text"
                placeholder="https://la-wall.com/ o un enlace de Google Docs"
                value={webSourceForm.root_url}
                onChange={(e) => setWebSourceForm({ ...webSourceForm, root_url: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="web-source-max-pages">Máximo de páginas a rastrear</label>
              <input
                id="web-source-max-pages"
                type="number"
                min={1}
                value={webSourceForm.max_pages}
                onChange={(e) =>
                  setWebSourceForm({ ...webSourceForm, max_pages: Number(e.target.value) })
                }
                required
              />
              <span style={{ fontSize: 12, color: "var(--color-muted)" }}>
                No aplica a enlaces de Google Docs.
              </span>
            </div>
          </div>
          <div className="btn-row">
            <button type="submit" className="btn btn-primary" disabled={createWebSourceMutation.isPending}>
              {createWebSourceMutation.isPending ? "Rastreando…" : "Guardar"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setShowWebSourceForm(false);
                setWebSourceForm(EMPTY_WEB_SOURCE_FORM);
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoadingWebSources && <p>Cargando…</p>}

      {webSources && webSources.length === 0 && !showWebSourceForm && (
        <div className="empty-state">No hay ninguna web configurada todavía.</div>
      )}

      {webSources && webSources.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>URL raíz</th>
              <th>Páginas rastreadas</th>
              <th>Texto extraído</th>
              <th>Estado</th>
              <th>Última actualización</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {webSources.map((source) => (
              <tr key={source.id}>
                <td>{source.name}</td>
                <td>{source.root_url}</td>
                <td>{source.pages_crawled ?? "—"}</td>
                <td>{source.text_length.toLocaleString("es-ES")} caracteres</td>
                <td>
                  <span className={`badge ${source.is_active ? "tone-success" : "tone-neutral"}`}>
                    {source.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>{formatDateTime(source.last_fetched_at)}</td>
                <td>
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => refreshWebSourceMutation.mutate(source.id)}
                    >
                      Actualizar ahora
                    </button>
                    {source.is_active ? (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => deactivateWebSourceMutation.mutate(source.id)}
                      >
                        Desactivar
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => activateWebSourceMutation.mutate(source.id)}
                      >
                        Activar
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        if (confirm(`¿Eliminar la fuente web "${source.name}"?`)) {
                          deleteWebSourceMutation.mutate(source.id);
                        }
                      }}
                    >
                      Eliminar
                    </button>
                  </div>
                  {source.last_fetch_error && (
                    <p className="error-text" style={{ marginTop: 6, fontSize: 12 }}>
                      {source.last_fetch_error}
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
