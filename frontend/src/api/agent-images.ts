import { apiClient } from "./client";
import type { AgentImage } from "../types";

export async function listAgentImages(): Promise<AgentImage[]> {
  const { data } = await apiClient.get<AgentImage[]>("/agent-images");
  return data;
}

export async function createAgentImage(params: {
  name: string;
  description: string;
  file: File;
}): Promise<AgentImage> {
  const formData = new FormData();
  formData.append("name", params.name);
  formData.append("description", params.description);
  formData.append("file", params.file);
  const { data } = await apiClient.post<AgentImage>("/agent-images", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteAgentImage(id: number): Promise<void> {
  await apiClient.delete(`/agent-images/${id}`);
}

// A plain <img src> won't carry the Authorization header the axios
// interceptor adds, and the preview would otherwise be unreachable without
// exposing the image publicly — fetch it as a blob and hand back an object
// URL instead. Callers must revoke the URL when done with it.
export async function fetchAgentImagePreview(id: number): Promise<string | null> {
  try {
    const { data } = await apiClient.get<Blob>(`/agent-images/${id}/preview`, { responseType: "blob" });
    return URL.createObjectURL(data);
  } catch {
    return null;
  }
}
