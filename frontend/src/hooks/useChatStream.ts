import { useCallback, useEffect, useRef, useState } from "react";
import { startChatStream, startRetryStream, type StreamHandle } from "@/api/chatStream";

interface StreamingState {
  active: boolean;
  reply: string;
  reasoning: string;
  error: string | null;
  pendingUserMessage: string | null;
  pendingFileNames: string[];
}

const initial: StreamingState = {
  active: false,
  reply: "",
  reasoning: "",
  error: null,
  pendingUserMessage: null,
  pendingFileNames: [],
};

// 50ms 节流刷新一次 React state，避免高频 setState 卡顿
const FLUSH_INTERVAL_MS = 50;

interface UseChatStreamOptions {
  onDone?: (reply: string) => void;
  onUsage?: (input: number, output: number) => void;
}

export function useChatStream(opts: UseChatStreamOptions = {}) {
  const handleRef = useRef<StreamHandle | null>(null);
  const replyRef = useRef("");
  const reasoningRef = useRef("");
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<StreamingState>(initial);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current != null) return;
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      setState((prev) => ({
        ...prev,
        reply: replyRef.current,
        reasoning: reasoningRef.current,
      }));
    }, FLUSH_INTERVAL_MS);
  }, []);

  const reset = useCallback(() => {
    replyRef.current = "";
    reasoningRef.current = "";
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setState(initial);
  }, []);

  const send = useCallback(
    (req: Parameters<typeof startChatStream>[0], fileNames: string[] = []) => {
      handleRef.current?.abort();
      reset();
      setState({
        active: true,
        reply: "",
        reasoning: "",
        error: null,
        pendingUserMessage: req.content,
        pendingFileNames: fileNames,
      });

      handleRef.current = startChatStream(req, {
        onDelta: (text) => {
          replyRef.current += text;
          scheduleFlush();
        },
        onReasoning: (text) => {
          reasoningRef.current += text;
          scheduleFlush();
        },
        onUsage: (input, output) => opts.onUsage?.(input, output),
        onDone: (reply) => {
          replyRef.current = reply || replyRef.current;
          if (flushTimerRef.current) {
            clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          setState((prev) => ({
            active: false,
            reply: replyRef.current,
            reasoning: reasoningRef.current,
            error: prev.error,
            pendingUserMessage: null,
            pendingFileNames: [],
          }));
          opts.onDone?.(replyRef.current);
        },
        onError: (error) => {
          if (flushTimerRef.current) {
            clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          setState((prev) => ({
            active: false,
            reply: replyRef.current,
            reasoning: reasoningRef.current,
            error,
            pendingUserMessage: prev.pendingUserMessage,
            pendingFileNames: prev.pendingFileNames,
          }));
        },
      });
    },
    [opts, reset, scheduleFlush],
  );

  const retry = useCallback(
    (conversationId: number) => {
      handleRef.current?.abort();
      reset();
      setState({ ...initial, active: true });

      handleRef.current = startRetryStream(conversationId, {
        onDelta: (text) => {
          replyRef.current += text;
          scheduleFlush();
        },
        onReasoning: (text) => {
          reasoningRef.current += text;
          scheduleFlush();
        },
        onUsage: (input, output) => opts.onUsage?.(input, output),
        onDone: (reply) => {
          replyRef.current = reply || replyRef.current;
          if (flushTimerRef.current) {
            clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          setState((prev) => ({
            active: false,
            reply: replyRef.current,
            reasoning: reasoningRef.current,
            error: prev.error,
            pendingUserMessage: null,
            pendingFileNames: [],
          }));
          opts.onDone?.(replyRef.current);
        },
        onError: (error) => {
          if (flushTimerRef.current) {
            clearTimeout(flushTimerRef.current);
            flushTimerRef.current = null;
          }
          setState({
            ...initial,
            active: false,
            reply: replyRef.current,
            reasoning: reasoningRef.current,
            error,
          });
        },
      });
    },
    [opts, reset, scheduleFlush],
  );

  const abort = useCallback(() => {
    handleRef.current?.abort();
  }, []);

  useEffect(() => {
    return () => {
      handleRef.current?.abort();
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    };
  }, []);

  return { ...state, send, retry, abort, reset };
}
