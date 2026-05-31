import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listConversations,
  createConversation,
  updateConversation,
  deleteConversation,
  fetchMessages,
} from "@/api/conversation";

export function useConversations(query: string) {
  return useQuery({
    queryKey: ["conversations", query],
    queryFn: () => listConversations(query),
    staleTime: 5_000,
  });
}

export function useConversationMessages(id: number | null) {
  return useQuery({
    queryKey: ["conversation-messages", id],
    queryFn: () => fetchMessages(id as number),
    enabled: id != null,
    staleTime: 0,
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createConversation,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useUpdateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: Parameters<typeof updateConversation>) =>
      updateConversation(vars[0], vars[1]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}
