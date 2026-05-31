// SSE 事件类型，与后端 chat.py 中 sse_payload 输出对齐
export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "reasoning"; text: string }
  | { type: "usage"; input_tokens: number; output_tokens: number }
  | { type: "done"; reply: string }
  | { type: "error"; error: string };
