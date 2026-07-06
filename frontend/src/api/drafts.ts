import { apiClient } from "./client";
import type { Draft, DraftListItem } from "../types";

export async function listDrafts(): Promise<DraftListItem[]> {
  const { data } = await apiClient.get<DraftListItem[]>("/drafts");
  return data;
}

export async function getDraft(id: number): Promise<Draft> {
  const { data } = await apiClient.get<Draft>(`/drafts/${id}`);
  return data;
}
