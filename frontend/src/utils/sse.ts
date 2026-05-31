// SSE 帧解析：按 `\n\n` 分隔事件，提取 event/data 行。
// rest 是缓冲剩余部分，下次调用时拼回再继续解析。

export interface SseFrame {
  event: string;
  data: string;
}

export function parseSseChunks(buffer: string): { events: SseFrame[]; rest: string } {
  const events: SseFrame[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";

  for (const part of parts) {
    if (!part.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (dataLines.length > 0) {
      events.push({ event, data: dataLines.join("\n") });
    }
  }
  return { events, rest };
}
