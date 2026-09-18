import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { createAgentImage, deleteAgentImage, fetchAgentImagePreview, listAgentImages } from "../api/agent-images";
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
import { getErrorMessage } from "../utils/getErrorMessage";

const ACCEPTED_EXTENSIONS = ".txt,.md,.pdf,.docx,.xlsx";
const ACCEPTED_IMAGE_EXTENSIONS = ".png,.jpg,.jpeg";

const EMPTY_WEB_SOURCE_FORM: WebSourceFormValues = {
  name: "",
  root_url: "",
  max_pages: 20,
};

const EMPTY_DRIVE_FORM = { name: "", root_url: "" };
const EMPTY_AGENT_IMAGE_FORM = { name: "", description: "" };

function isGoogleDocsSource(rootUrl: string): boolean {
  try {
    const host = new URL(rootUrl).hostname;
    return host === "docs.google.com" || host === "drive.google.com";
  } catch {
    return false;
  }
}

function AgentImageThumbnail({ imageId, name }: { imageId: number; name: string }) {
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

  if (!previewUrl) return <span className="page-subtitle">—</span>;
  return <img src={previewUrl} alt={name} style={{ maxWidth: 80, maxHeight: 50, borderRadius: 4 }} />;
}

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
  const [webSourceFormError, setWebSourceFormError] = useState<string | null>(null);

  const invalidateWebSources = () => queryClient.invalidateQueries({ queryKey: ["web-sources"] });

  const createWebSourceMutation = useMutation({
    mutationFn: createWebSource,
    onSuccess: () => {
      invalidateWebSources();
      setShowWebSourceForm(false);
      setWebSourceForm(EMPTY_WEB_SOURCE_FORM);
      setWebSourceFormError(null);
    },
    onError: (error) =>
      setWebSourceFormError(getErrorMessage(error, "No se pudo crear la fuente web.")),
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
    setWebSourceFormError(null);
    createWebSourceMutation.mutate(webSourceForm);
  }

  const regularWebSources = webSources?.filter((source) => !isGoogleDocsSource(source.root_url));
  const driveSources = webSources?.filter((source) => isGoogleDocsSource(source.root_url));

  // --- Drive documents ----------------------------------------------------
  const [showDriveForm, setShowDriveForm] = useState(false);
  const [driveForm, setDriveForm] = useState(EMPTY_DRIVE_FORM);
  const [driveFormError, setDriveFormError] = useState<string | null>(null);

  const createDriveSourceMutation = useMutation({
    mutationFn: createWebSource,
    onSuccess: () => {
      invalidateWebSources();
      setShowDriveForm(false);
      setDriveForm(EMPTY_DRIVE_FORM);
      setDriveFormError(null);
    },
    onError: (error) =>
      setDriveFormError(getErrorMessage(error, "No se pudo añadir el documento de Drive.")),
  });

  function handleDriveSubmit(event: FormEvent) {
    event.preventDefault();
    setDriveFormError(null);
    createDriveSourceMutation.mutate({ ...driveForm, max_pages: 20 });
  }

  // --- Agent images -------------------------------------------------------
  const { data: agentImages, isLoading: isLoadingAgentImages } = useQuery({
    queryKey: ["agent-images"],
    queryFn: listAgentImages,
  });
  const [showAgentImageForm, setShowAgentImageForm] = useState(false);
  const [agentImageForm, setAgentImageForm] = useState(EMPTY_AGENT_IMAGE_FORM);
  const [agentImageFormError, setAgentImageFormError] = useState<string | null>(null);
  const agentImageFileInputRef = useRef<HTMLInputElement>(null);

  const invalidateAgentImages = () => queryClient.invalidateQueries({ queryKey: ["agent-images"] });

  const createAgentImageMutation = useMutation({
    mutationFn: createAgentImage,
    onSuccess: () => {
      invalidateAgentImages();
      setShowAgentImageForm(false);
      setAgentImageForm(EMPTY_AGENT_IMAGE_FORM);
      setAgentImageFormError(null);
      if (agentImageFileInputRef.current) agentImageFileInputRef.current.value = "";
    },
    onError: (error) => setAgentImageFormError(getErrorMessage(error, "No se pudo subir la imagen.")),
  });
  const deleteAgentImageMutation = useMutation({ mutationFn: deleteAgentImage, onSuccess: invalidateAgentImages });

  function handleAgentImageSubmit(event: FormEvent) {
    event.preventDefault();
    setAgentImageFormError(null);
    const file = agentImageFileInputRef.current?.files?.[0];
    if (!file) {
      setAgentImageFormError("Selecciona un archivo de imagen.");
      return;
    }
    createAgentImageMutation.mutate({ ...agentImageForm, file });
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
            rastrean las páginas internas del mismo dominio y se actualizan periódicamente.
          </p>
        </div>
        {!showWebSourceForm && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setWebSourceFormError(null);
              setShowWebSourceForm(true);
            }}
          >
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
                placeholder="https://la-wall.com/"
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
            </div>
          </div>
          {webSourceFormError && <p className="error-text">{webSourceFormError}</p>}
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
                setWebSourceFormError(null);
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoadingWebSources && <p>Cargando…</p>}

      {regularWebSources && regularWebSources.length === 0 && !showWebSourceForm && (
        <div className="empty-state">No hay ninguna web configurada todavía.</div>
      )}

      {regularWebSources && regularWebSources.length > 0 && (
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
            {regularWebSources.map((source) => (
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

      <div className="page-header" style={{ marginTop: 40 }}>
        <div>
          <h2 style={{ marginTop: 0 }}>Documentos de Drive</h2>
          <p className="page-subtitle">
            Añade documentos de Google Docs para que el agente use su contenido como contexto. El
            documento debe estar compartido como "Cualquiera con el enlace puede ver"; su contenido se
            mantiene sincronizado en cada actualización periódica.
          </p>
        </div>
        {!showDriveForm && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setDriveFormError(null);
              setShowDriveForm(true);
            }}
          >
            Nuevo documento de Drive
          </button>
        )}
      </div>

      {showDriveForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleDriveSubmit}>
          <h3 style={{ marginTop: 0 }}>Nuevo documento de Drive</h3>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="drive-source-name">Nombre</label>
              <input
                id="drive-source-name"
                type="text"
                value={driveForm.name}
                onChange={(e) => setDriveForm({ ...driveForm, name: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="drive-source-url">Enlace al documento</label>
              <input
                id="drive-source-url"
                type="text"
                placeholder="https://docs.google.com/document/d/..."
                value={driveForm.root_url}
                onChange={(e) => setDriveForm({ ...driveForm, root_url: e.target.value })}
                required
              />
            </div>
          </div>
          {driveFormError && <p className="error-text">{driveFormError}</p>}
          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={createDriveSourceMutation.isPending}
            >
              {createDriveSourceMutation.isPending ? "Descargando…" : "Guardar"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setShowDriveForm(false);
                setDriveForm(EMPTY_DRIVE_FORM);
                setDriveFormError(null);
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoadingWebSources && <p>Cargando…</p>}

      {driveSources && driveSources.length === 0 && !showDriveForm && (
        <div className="empty-state">No hay documentos de Drive configurados todavía.</div>
      )}

      {driveSources && driveSources.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Enlace</th>
              <th>Texto extraído</th>
              <th>Estado</th>
              <th>Última actualización</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {driveSources.map((source) => (
              <tr key={source.id}>
                <td>{source.name}</td>
                <td>{source.root_url}</td>
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
                        if (confirm(`¿Eliminar el documento de Drive "${source.name}"?`)) {
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

      <div className="page-header" style={{ marginTop: 40 }}>
        <div>
          <h2 style={{ marginTop: 0 }}>Imágenes del agente</h2>
          <p className="page-subtitle">
            Imágenes que el agente puede incrustar en un borrador (por ejemplo, la tabla de precios
            en español o en inglés). Ponle un nombre y describe cuándo debe usarse — el agente
            decide en cada respuesta, según esa descripción, si corresponde adjuntar alguna. Para
            añadir un caso nuevo, sube la imagen aquí: no hace falta tocar nada más.
          </p>
        </div>
        {!showAgentImageForm && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setAgentImageFormError(null);
              setShowAgentImageForm(true);
            }}
          >
            Nueva imagen
          </button>
        )}
      </div>

      {showAgentImageForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleAgentImageSubmit}>
          <h3 style={{ marginTop: 0 }}>Nueva imagen</h3>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="agent-image-name">Nombre</label>
              <input
                id="agent-image-name"
                type="text"
                placeholder="Tabla de precios (Español)"
                value={agentImageForm.name}
                onChange={(e) => setAgentImageForm({ ...agentImageForm, name: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="agent-image-description">¿Cuándo debe usarse?</label>
              <textarea
                id="agent-image-description"
                placeholder="Usar cuando el cliente pregunte por precios y el correo esté en español."
                value={agentImageForm.description}
                onChange={(e) => setAgentImageForm({ ...agentImageForm, description: e.target.value })}
                style={{ width: "100%", minHeight: 70 }}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="agent-image-file">Imagen (PNG o JPG)</label>
              <input
                ref={agentImageFileInputRef}
                id="agent-image-file"
                type="file"
                accept={ACCEPTED_IMAGE_EXTENSIONS}
                required
              />
            </div>
          </div>
          {agentImageFormError && <p className="error-text">{agentImageFormError}</p>}
          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={createAgentImageMutation.isPending}
            >
              {createAgentImageMutation.isPending ? "Subiendo…" : "Guardar"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setShowAgentImageForm(false);
                setAgentImageForm(EMPTY_AGENT_IMAGE_FORM);
                setAgentImageFormError(null);
              }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoadingAgentImages && <p>Cargando…</p>}

      {agentImages && agentImages.length === 0 && !showAgentImageForm && (
        <div className="empty-state">No hay imágenes configuradas todavía.</div>
      )}

      {agentImages && agentImages.length > 0 && (
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Nombre</th>
              <th>Cuándo se usa</th>
              <th>Subida</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {agentImages.map((image) => (
              <tr key={image.id}>
                <td>
                  <AgentImageThumbnail imageId={image.id} name={image.name} />
                </td>
                <td>{image.name}</td>
                <td style={{ maxWidth: 360 }}>{image.description}</td>
                <td>{formatDateTime(image.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    onClick={() => {
                      if (confirm(`¿Eliminar la imagen "${image.name}"?`)) {
                        deleteAgentImageMutation.mutate(image.id);
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
    </div>
  );
}
