import { apiClient } from "./client";
import type { ProcessingDetail, ProcessingListItem } from "../types";

export async function listProcessing(): Promise<ProcessingListItem[]> {
  const { data } = await apiClient.get<ProcessingListItem[]>("/processing");
  return data;
}

export async function getProcessingDetail(emailMessageId: number): Promise<ProcessingDetail> {
  const { data } = await apiClient.get<ProcessingDetail>(`/processing/${emailMessageId}`);
  return data;
}
