import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/api/client";

interface AuthImageProps {
  src: string;
  alt?: string;
  style?: React.CSSProperties;
}

export function AuthImage({ src, alt, style }: AuthImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const revokeRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(src)
      .then((resp) => {
        if (!resp.ok) throw new Error(`${resp.status}`);
        return resp.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revokeRef.current = url;
        setBlobUrl(url);
      })
      .catch(() => {
        if (!cancelled) setBlobUrl(null);
      });
    return () => {
      cancelled = true;
      if (revokeRef.current) {
        URL.revokeObjectURL(revokeRef.current);
        revokeRef.current = null;
      }
    };
  }, [src]);

  if (!blobUrl) {
    return <span style={{ color: "#999", fontSize: 12 }}>{alt ?? "加载图片中…"}</span>;
  }

  return <img src={blobUrl} alt={alt} style={style} />;
}
