import { apiClient } from "./client";
import type { ProcessingDetail, ProcessingListItem, SimulateDraftResponse } from "../types";

export async function listProcessing(): Promise<ProcessingListItem[]> {
  const { data } = await apiClient.get<ProcessingListItem[]>("/processing");
  return data;
}

export async function getProcessingDetail(emailMessageId: number): Promise<ProcessingDetail> {
  const { data } = await apiClient.get<ProcessingDetail>(`/processing/${emailMessageId}`);
  return data;
}

export async function simulateDraft(emailBody: string): Promise<SimulateDraftResponse> {
  const { data } = await apiClient.post<SimulateDraftResponse>("/processing/simulate", {
    email_body: emailBody,
  });
  return data;
}
