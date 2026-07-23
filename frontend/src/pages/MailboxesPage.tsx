import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import {
  activateMailbox,
  createMailbox,
  deactivateMailbox,
  deleteMailbox,
  listMailboxes,
  testMailboxConnection,
  updateMailbox,
} from "../api/mailboxes";
import type { Mailbox, MailboxFormValues } from "../types";
import { formatDateTime } from "../utils/formatDate";
import { getErrorMessage } from "../utils/getErrorMessage";

const EMPTY_FORM: MailboxFormValues = {
  name: "",
  email_address: "",
  provider: "nominalia",
  imap_host: "",
  imap_port: 993,
  imap_username: "",
  imap_password: "",
  imap_use_ssl: true,
  inbox_folder: "INBOX",
  drafts_folder: "Drafts",
};

export default function MailboxesPage() {
  const queryClient = useQueryClient();
  const { data: mailboxes, isLoading } = useQuery({ queryKey: ["mailboxes"], queryFn: listMailboxes });

  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<MailboxFormValues>(EMPTY_FORM);
  const [testMessages, setTestMessages] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["mailboxes"] });

  const createMutation = useMutation({
    mutationFn: createMailbox,
    onSuccess: () => {
      invalidate();
      closeForm();
    },
    onError: (error) => setFormError(getErrorMessage(error, "No se pudo crear el buzón.")),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<MailboxFormValues> }) =>
      updateMailbox(id, payload),
    onSuccess: () => {
      invalidate();
      closeForm();
    },
    onError: (error) => setFormError(getErrorMessage(error, "No se pudo guardar el buzón.")),
  });

  const deleteMutation = useMutation({ mutationFn: deleteMailbox, onSuccess: invalidate });
  const activateMutation = useMutation({ mutationFn: activateMailbox, onSuccess: invalidate });
  const deactivateMutation = useMutation({ mutationFn: deactivateMailbox, onSuccess: invalidate });

  const testMutation = useMutation({
    mutationFn: testMailboxConnection,
    onSuccess: (result, id) => setTestMessages((prev) => ({ ...prev, [id]: result.message })),
    onError: (_err, id) =>
      setTestMessages((prev) => ({ ...prev, [id]: "No se pudo verificar la conexión." })),
  });

  function openCreateForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setShowForm(true);
  }

  function openEditForm(mailbox: Mailbox) {
    setEditingId(mailbox.id);
    setForm({
      name: mailbox.name,
      email_address: mailbox.email_address,
      provider: mailbox.provider,
      imap_host: mailbox.imap_host,
      imap_port: mailbox.imap_port,
      imap_username: mailbox.imap_username,
      imap_password: "",
      imap_use_ssl: mailbox.imap_use_ssl,
      inbox_folder: mailbox.inbox_folder,
      drafts_folder: mailbox.drafts_folder,
    });
    setFormError(null);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (editingId !== null) {
      const payload: Partial<MailboxFormValues> = { ...form };
      if (!payload.imap_password) delete payload.imap_password;
      updateMutation.mutate({ id: editingId, payload });
    } else {
      createMutation.mutate(form);
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Buzones</h1>
          <p className="page-subtitle">Configura los buzones de Nominalia que Walli debe vigilar.</p>
        </div>
        {!showForm && (
          <button type="button" className="btn btn-primary" onClick={openCreateForm}>
            Nuevo buzón
          </button>
        )}
      </div>

      {showForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleSubmit}>
          <h2>{editingId !== null ? "Editar buzón" : "Nuevo buzón"}</h2>
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="name">Nombre</label>
              <input
                id="name"
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="email_address">Email</label>
              <input
                id="email_address"
                type="text"
                value={form.email_address}
                onChange={(e) => setForm({ ...form, email_address: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="provider">Proveedor</label>
              <select
                id="provider"
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value as Mailbox["provider"] })}
              >
                <option value="nominalia">Nominalia</option>
                <option value="generic_imap">IMAP genérico</option>
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="imap_host">IMAP host</label>
              <input
                id="imap_host"
                type="text"
                value={form.imap_host}
                onChange={(e) => setForm({ ...form, imap_host: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="imap_port">IMAP port</label>
              <input
                id="imap_port"
                type="number"
                value={form.imap_port}
                onChange={(e) => setForm({ ...form, imap_port: Number(e.target.value) })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="imap_username">IMAP username</label>
              <input
                id="imap_username"
                type="text"
                value={form.imap_username}
                onChange={(e) => setForm({ ...form, imap_username: e.target.value })}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="imap_password">
                IMAP password {editingId !== null && "(dejar vacío para no cambiar)"}
              </label>
              <input
                id="imap_password"
                type="password"
                value={form.imap_password}
                onChange={(e) => setForm({ ...form, imap_password: e.target.value })}
                required={editingId === null}
              />
            </div>
            <div className="form-field">
              <label htmlFor="inbox_folder">Carpeta de entrada</label>
              <input
                id="inbox_folder"
                type="text"
                value={form.inbox_folder}
                onChange={(e) => setForm({ ...form, inbox_folder: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label htmlFor="drafts_folder">Carpeta de borradores</label>
              <input
                id="drafts_folder"
                type="text"
                value={form.drafts_folder}
                onChange={(e) => setForm({ ...form, drafts_folder: e.target.value })}
              />
            </div>
            <div className="form-field checkbox-field">
              <input
                id="imap_use_ssl"
                type="checkbox"
                checked={form.imap_use_ssl}
                onChange={(e) => setForm({ ...form, imap_use_ssl: e.target.checked })}
              />
              <label htmlFor="imap_use_ssl">Usar SSL</label>
            </div>
          </div>
          {formError && <p className="error-text">{formError}</p>}
          <div className="btn-row">
            <button type="submit" className="btn btn-primary" disabled={isSaving}>
              {isSaving ? "Guardando…" : "Guardar"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={closeForm}>
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoading && <p>Cargando…</p>}

      {mailboxes && mailboxes.length === 0 && !showForm && (
        <div className="empty-state">No hay buzones configurados todavía.</div>
      )}

      {mailboxes && mailboxes.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Email</th>
              <th>IMAP</th>
              <th>Estado</th>
              <th>Última revisión</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {mailboxes.map((mailbox) => (
              <tr key={mailbox.id}>
                <td>{mailbox.name}</td>
                <td>{mailbox.email_address}</td>
                <td>
                  {mailbox.imap_host}:{mailbox.imap_port}
                </td>
                <td>
                  <span className={`badge ${mailbox.is_active ? "tone-success" : "tone-neutral"}`}>
                    {mailbox.is_active ? "Activo" : "Inactivo"}
                  </span>
                  {mailbox.last_poll_error && (
                    <span className="badge tone-danger" style={{ marginLeft: 6 }}>
                      Error de conexión
                    </span>
                  )}
                </td>
                <td>{formatDateTime(mailbox.last_checked_at)}</td>
                <td>
                  <div className="btn-row">
                    <button type="button" className="btn btn-small" onClick={() => openEditForm(mailbox)}>
                      Editar
                    </button>
                    {mailbox.is_active ? (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => deactivateMutation.mutate(mailbox.id)}
                      >
                        Desactivar
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => activateMutation.mutate(mailbox.id)}
                      >
                        Activar
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => testMutation.mutate(mailbox.id)}
                    >
                      Probar conexión
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        if (confirm(`¿Eliminar el buzón "${mailbox.name}"?`)) {
                          deleteMutation.mutate(mailbox.id);
                        }
                      }}
                    >
                      Eliminar
                    </button>
                  </div>
                  {testMessages[mailbox.id] && (
                    <p className="page-subtitle" style={{ marginTop: 6, fontSize: 12 }}>
                      {testMessages[mailbox.id]}
                    </p>
                  )}
                  {mailbox.last_poll_error && (
                    <p className="error-text" style={{ marginTop: 6, fontSize: 12 }}>
                      Último sondeo fallido: {mailbox.last_poll_error}
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
