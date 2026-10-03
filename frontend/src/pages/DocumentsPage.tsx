import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  activateDriveSource,
  createDriveSource,
  deactivateDriveSource,
  deleteDriveSource,
  listDriveSources,
  syncDriveSource,
} from "../api/drive-sources";
import { deleteDocument, listDocuments, uploadDocument } from "../api/documents";
import type { DriveSourceFormValues } from "../types";
import { formatDateTime } from "../utils/formatDate";
import { getErrorMessage } from "../utils/getErrorMessage";

// Must mirror SUPPORTED_FILE_EXTENSIONS in backend/app/core/supported_file_types.py
// — the exact file types OpenAI's code_interpreter tool can actually read.
// Anything outside this list would just be dead weight the agent can never use.
const ACCEPTED_EXTENSIONS =
  ".doc,.docx,.pdf,.pptx,.csv,.json,.xml,.xlsx,.c,.cs,.cpp,.java,.py,.php,.rb,.js,.ts,.sh,.tex," +
  ".jpeg,.jpg,.gif,.png,.html,.md,.txt,.css,.pkl,.tar,.zip";

// Mirrors settings.max_upload_file_bytes (OpenAI Files API's hard cap) so an
// oversized file is rejected here, before ever hitting the network.
const MAX_UPLOAD_FILE_BYTES = 512 * 1024 * 1024;

const EMPTY_DRIVE_FORM: DriveSourceFormValues = { name: "", drive_url: "" };

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadStatusBadge({
  openaiFileId,
  uploadError,
}: {
  openaiFileId: string | null;
  uploadError?: string | null;
}) {
  if (uploadError) {
    return <span className="badge tone-danger">Error al subir a OpenAI</span>;
  }
  if (openaiFileId) {
    return <span className="badge tone-success">Subido a OpenAI</span>;
  }
  return <span className="badge tone-neutral">Pendiente</span>;
}

export default function DocumentsPage() {
  const queryClient = useQueryClient();

  // --- Archivos locales del agente --------------------------------------
  const { data: documents, isLoading } = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const invalidateDocuments = () => queryClient.invalidateQueries({ queryKey: ["documents"] });

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      invalidateDocuments();
      setUploadError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (error) => setUploadError(getErrorMessage(error, "No se pudo subir el documento.")),
  });

  const deleteMutation = useMutation({ mutationFn: deleteDocument, onSuccess: invalidateDocuments });

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_UPLOAD_FILE_BYTES) {
      setUploadError(
        `El archivo supera el tamaño máximo permitido (${MAX_UPLOAD_FILE_BYTES / (1024 * 1024)}MB).`
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setUploadError(null);
    uploadMutation.mutate(file);
  }

  // --- Archivos en Drive --------------------------------------------------
  const { data: driveSources, isLoading: isLoadingDriveSources } = useQuery({
    queryKey: ["drive-sources"],
    queryFn: listDriveSources,
  });
  const [showDriveForm, setShowDriveForm] = useState(false);
  const [driveForm, setDriveForm] = useState<DriveSourceFormValues>(EMPTY_DRIVE_FORM);
  const [driveFormError, setDriveFormError] = useState<string | null>(null);

  const invalidateDriveSources = () => queryClient.invalidateQueries({ queryKey: ["drive-sources"] });

  const createDriveSourceMutation = useMutation({
    mutationFn: createDriveSource,
    onSuccess: () => {
      invalidateDriveSources();
      setShowDriveForm(false);
      setDriveForm(EMPTY_DRIVE_FORM);
      setDriveFormError(null);
    },
    onError: (error) => setDriveFormError(getErrorMessage(error, "No se pudo añadir el archivo de Drive.")),
  });
  const deleteDriveSourceMutation = useMutation({
    mutationFn: deleteDriveSource,
    onSuccess: invalidateDriveSources,
  });
  const activateDriveSourceMutation = useMutation({
    mutationFn: activateDriveSource,
    onSuccess: invalidateDriveSources,
  });
  const deactivateDriveSourceMutation = useMutation({
    mutationFn: deactivateDriveSource,
    onSuccess: invalidateDriveSources,
  });
  const syncDriveSourceMutation = useMutation({
    mutationFn: syncDriveSource,
    onSuccess: invalidateDriveSources,
  });

  function handleDriveSubmit(event: FormEvent) {
    event.preventDefault();
    setDriveFormError(null);
    createDriveSourceMutation.mutate(driveForm);
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Archivos locales del agente</h1>
          <p className="page-subtitle">
            Sube los documentos que el agente debe poder consultar directamente (cualquier tipo de
            archivo que sepa leer: Word, Excel, PDF, imágenes, CSV...), hasta{" "}
            {MAX_UPLOAD_FILE_BYTES / (1024 * 1024)}MB por archivo.
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
            {uploadMutation.isPending ? "Subiendo…" : "Subir archivo"}
          </label>
        </div>
      </div>

      {uploadError && <p className="error-text">{uploadError}</p>}
      {isLoading && <p>Cargando…</p>}

      {documents && documents.length === 0 && (
        <div className="empty-state">No hay archivos locales cargados todavía.</div>
      )}

      {documents && documents.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Archivo</th>
              <th>Tamaño</th>
              <th>Estado</th>
              <th>Subida a OpenAI</th>
              <th>Subido</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.original_filename}</td>
                <td>{formatBytes(doc.size_bytes)}</td>
                <td>
                  <span className={`badge ${doc.is_active ? "tone-success" : "tone-neutral"}`}>
                    {doc.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>
                  <UploadStatusBadge openaiFileId={doc.openai_file_id} uploadError={doc.openai_upload_error} />
                  {doc.openai_upload_error && (
                    <p className="error-text" style={{ marginTop: 4, fontSize: 12 }}>
                      {doc.openai_upload_error}
                    </p>
                  )}
                </td>
                <td>{formatDateTime(doc.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    onClick={() => {
                      if (confirm(`¿Eliminar el archivo "${doc.original_filename}"?`)) {
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
          <h2 style={{ marginTop: 0 }}>Archivos en Drive</h2>
          <p className="page-subtitle">
            Pega el enlace a un archivo de Google Drive (compartido como "Cualquiera con el enlace
            puede ver"), un Google Doc, una Hoja de cálculo o una Presentación. Se comprueba cada
            minuto si ha cambiado y, si es así, se actualiza automáticamente.
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
            Nuevo archivo de Drive
          </button>
        )}
      </div>

      {showDriveForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleDriveSubmit}>
          <h3 style={{ marginTop: 0 }}>Nuevo archivo de Drive</h3>
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
              <label htmlFor="drive-source-url">Enlace de Drive</label>
              <input
                id="drive-source-url"
                type="text"
                placeholder="https://drive.google.com/file/d/... o https://docs.google.com/document/d/..."
                value={driveForm.drive_url}
                onChange={(e) => setDriveForm({ ...driveForm, drive_url: e.target.value })}
                required
              />
            </div>
          </div>
          {driveFormError && <p className="error-text">{driveFormError}</p>}
          <div className="btn-row">
            <button type="submit" className="btn btn-primary" disabled={createDriveSourceMutation.isPending}>
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

      {isLoadingDriveSources && <p>Cargando…</p>}

      {driveSources && driveSources.length === 0 && !showDriveForm && (
        <div className="empty-state">No hay ningún archivo de Drive configurado todavía.</div>
      )}

      {driveSources && driveSources.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Enlace</th>
              <th>Tamaño</th>
              <th>Estado</th>
              <th>Subida a OpenAI</th>
              <th>Última comprobación</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {driveSources.map((source) => (
              <tr key={source.id}>
                <td>{source.name}</td>
                <td style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {source.drive_url}
                </td>
                <td>{formatBytes(source.size_bytes)}</td>
                <td>
                  <span className={`badge ${source.is_active ? "tone-success" : "tone-neutral"}`}>
                    {source.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>
                  <UploadStatusBadge openaiFileId={source.openai_file_id} uploadError={source.last_sync_error} />
                  {source.last_sync_error && (
                    <p className="error-text" style={{ marginTop: 4, fontSize: 12 }}>
                      {source.last_sync_error}
                    </p>
                  )}
                </td>
                <td>{formatDateTime(source.last_checked_at)}</td>
                <td>
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => syncDriveSourceMutation.mutate(source.id)}
                    >
                      Sincronizar ahora
                    </button>
                    {source.is_active ? (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => deactivateDriveSourceMutation.mutate(source.id)}
                      >
                        Desactivar
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => activateDriveSourceMutation.mutate(source.id)}
                      >
                        Activar
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        if (confirm(`¿Eliminar el archivo de Drive "${source.name}"?`)) {
                          deleteDriveSourceMutation.mutate(source.id);
                        }
                      }}
                    >
                      Eliminar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
