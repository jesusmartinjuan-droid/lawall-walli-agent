import { apiClient } from "./client";
import type { PromptTemplate } from "../types";

export interface PromptFormValues {
  name: string;
  description?: string | null;
  content: string;
  is_active: boolean;
}

export async function listPrompts(): Promise<PromptTemplate[]> {
  const { data } = await apiClient.get<PromptTemplate[]>("/prompts");
  return data;
}

export async function createPrompt(payload: PromptFormValues): Promise<PromptTemplate> {
  const { data } = await apiClient.post<PromptTemplate>("/prompts", payload);
  return data;
}

export async function updatePrompt(
  id: number,
  payload: Partial<PromptFormValues>,
): Promise<PromptTemplate> {
  const { data } = await apiClient.put<PromptTemplate>(`/prompts/${id}`, payload);
  return data;
}

export async function deletePrompt(id: number): Promise<void> {
  await apiClient.delete(`/prompts/${id}`);
}

export async function setActivePrompt(id: number): Promise<PromptTemplate> {
  const { data } = await apiClient.post<PromptTemplate>(`/prompts/${id}/set-active`);
  return data;
}
