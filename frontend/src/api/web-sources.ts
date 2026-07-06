import { apiClient } from "./client";
import type { WebSource, WebSourceFormValues } from "../types";

export async function listWebSources(): Promise<WebSource[]> {
  const { data } = await apiClient.get<WebSource[]>("/web-sources");
  return data;
}

export async function createWebSource(payload: WebSourceFormValues): Promise<WebSource> {
  const { data } = await apiClient.post<WebSource>("/web-sources", payload);
  return data;
}

export async function deleteWebSource(id: number): Promise<void> {
  await apiClient.delete(`/web-sources/${id}`);
}

export async function activateWebSource(id: number): Promise<WebSource> {
  const { data } = await apiClient.post<WebSource>(`/web-sources/${id}/activate`);
  return data;
}

export async function deactivateWebSource(id: number): Promise<WebSource> {
  const { data } = await apiClient.post<WebSource>(`/web-sources/${id}/deactivate`);
  return data;
}

export async function refreshWebSource(id: number): Promise<WebSource> {
  const { data } = await apiClient.post<WebSource>(`/web-sources/${id}/refresh`);
  return data;
}
