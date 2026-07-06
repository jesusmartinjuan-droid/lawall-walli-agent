import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import {
  createPrompt,
  deletePrompt,
  listPrompts,
  setActivePrompt,
  updatePrompt,
} from "../api/prompts";
import type { PromptFormValues } from "../api/prompts";
import type { PromptTemplate } from "../types";
import { formatDateTime } from "../utils/formatDate";

const EMPTY_FORM: PromptFormValues = {
  name: "",
  description: "",
  content: "",
  is_active: true,
};

export default function PromptsPage() {
  const queryClient = useQueryClient();
  const { data: prompts, isLoading } = useQuery({ queryKey: ["prompts"], queryFn: listPrompts });

  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<PromptFormValues>(EMPTY_FORM);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["prompts"] });

  const createMutation = useMutation({ mutationFn: createPrompt, onSuccess: () => { invalidate(); closeForm(); } });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<PromptFormValues> }) =>
      updatePrompt(id, payload),
    onSuccess: () => {
      invalidate();
      closeForm();
    },
  });
  const deleteMutation = useMutation({ mutationFn: deletePrompt, onSuccess: invalidate });
  const setActiveMutation = useMutation({ mutationFn: setActivePrompt, onSuccess: invalidate });

  function openCreateForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  function openEditForm(prompt: PromptTemplate) {
    setEditingId(prompt.id);
    setForm({
      name: prompt.name,
      description: prompt.description ?? "",
      content: prompt.content,
      is_active: prompt.is_active,
    });
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (editingId !== null) {
      updateMutation.mutate({ id: editingId, payload: form });
    } else {
      createMutation.mutate(form);
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Prompts</h1>
          <p className="page-subtitle">Gestiona los prompts usados para generar los borradores.</p>
        </div>
        {!showForm && (
          <button type="button" className="btn btn-primary" onClick={openCreateForm}>
            Nuevo prompt
          </button>
        )}
      </div>

      {showForm && (
        <form className="card" style={{ marginBottom: 24 }} onSubmit={handleSubmit}>
          <h2>{editingId !== null ? "Editar prompt" : "Nuevo prompt"}</h2>
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
              <label htmlFor="description">Descripción</label>
              <input
                id="description"
                type="text"
                value={form.description ?? ""}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            <div className="form-field checkbox-field">
              <input
                id="is_active"
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              <label htmlFor="is_active">Activo</label>
            </div>
            <div className="form-field full-width">
              <label htmlFor="content">Contenido</label>
              <textarea
                id="content"
                value={form.content}
                onChange={(e) => setForm({ ...form, content: e.target.value })}
                rows={12}
                required
              />
            </div>
          </div>
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

      {prompts && prompts.length === 0 && !showForm && (
        <div className="empty-state">No hay prompts configurados todavía.</div>
      )}

      {prompts && prompts.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Descripción</th>
              <th>Estado</th>
              <th>Activo para generación</th>
              <th>Actualizado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr key={prompt.id}>
                <td>{prompt.name}</td>
                <td>{prompt.description ?? "—"}</td>
                <td>
                  <span className={`badge ${prompt.is_active ? "tone-success" : "tone-neutral"}`}>
                    {prompt.is_active ? "Activo" : "Inactivo"}
                  </span>
                </td>
                <td>
                  {prompt.is_default ? (
                    <span className="badge tone-info">Prompt activo</span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => setActiveMutation.mutate(prompt.id)}
                    >
                      Marcar como activo
                    </button>
                  )}
                </td>
                <td>{formatDateTime(prompt.updated_at)}</td>
                <td>
                  <div className="btn-row">
                    <button type="button" className="btn btn-small" onClick={() => openEditForm(prompt)}>
                      Editar
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        if (confirm(`¿Eliminar el prompt "${prompt.name}"?`)) {
                          deleteMutation.mutate(prompt.id);
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
