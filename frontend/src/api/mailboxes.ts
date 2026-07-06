import { apiClient } from "./client";
import type { Mailbox, MailboxFormValues } from "../types";

export async function listMailboxes(): Promise<Mailbox[]> {
  const { data } = await apiClient.get<Mailbox[]>("/mailboxes");
  return data;
}

export async function createMailbox(payload: MailboxFormValues): Promise<Mailbox> {
  const { data } = await apiClient.post<Mailbox>("/mailboxes", payload);
  return data;
}

export async function updateMailbox(
  id: number,
  payload: Partial<MailboxFormValues>,
): Promise<Mailbox> {
  const { data } = await apiClient.put<Mailbox>(`/mailboxes/${id}`, payload);
  return data;
}

export async function deleteMailbox(id: number): Promise<void> {
  await apiClient.delete(`/mailboxes/${id}`);
}

export async function activateMailbox(id: number): Promise<Mailbox> {
  const { data } = await apiClient.post<Mailbox>(`/mailboxes/${id}/activate`);
  return data;
}

export async function deactivateMailbox(id: number): Promise<Mailbox> {
  const { data } = await apiClient.post<Mailbox>(`/mailboxes/${id}/deactivate`);
  return data;
}

export async function testMailboxConnection(
  id: number,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    `/mailboxes/${id}/test-connection`,
  );
  return data;
}
