import { apiClient } from "./client";
import type { DriveSource, DriveSourceFormValues } from "../types";

export async function listDriveSources(): Promise<DriveSource[]> {
  const { data } = await apiClient.get<DriveSource[]>("/drive-sources");
  return data;
}

export async function createDriveSource(payload: DriveSourceFormValues): Promise<DriveSource> {
  const { data } = await apiClient.post<DriveSource>("/drive-sources", payload);
  return data;
}

export async function deleteDriveSource(id: number): Promise<void> {
  await apiClient.delete(`/drive-sources/${id}`);
}

export async function activateDriveSource(id: number): Promise<DriveSource> {
  const { data } = await apiClient.post<DriveSource>(`/drive-sources/${id}/activate`);
  return data;
}

export async function deactivateDriveSource(id: number): Promise<DriveSource> {
  const { data } = await apiClient.post<DriveSource>(`/drive-sources/${id}/deactivate`);
  return data;
}

export async function syncDriveSource(id: number): Promise<DriveSource> {
  const { data } = await apiClient.post<DriveSource>(`/drive-sources/${id}/sync`);
  return data;
}
