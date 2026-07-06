import { apiClient } from "./client";
import type { DocumentItem } from "../types";

export async function listDocuments(): Promise<DocumentItem[]> {
  const { data } = await apiClient.get<DocumentItem[]>("/documents");
  return data;
}

export async function uploadDocument(file: File): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<DocumentItem>("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteDocument(id: number): Promise<void> {
  await apiClient.delete(`/documents/${id}`);
}
