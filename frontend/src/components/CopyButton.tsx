import { useEffect, useRef, useState, type ReactNode } from "react";
import { copyText } from "@/lib/clipboard";

interface Props {
  value: string;
  timeout?: number;
  children: (p: { copied: boolean; failed: boolean; copy: () => void }) => ReactNode;
}

export function CopyButton({ value, timeout = 1500, children }: Props) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = () => {
    void copyText(value).then((ok) => {
      setCopied(ok);
      setFailed(!ok);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => {
        setCopied(false);
        setFailed(false);
      }, timeout);
    });
  };
  return <>{children({ copied, failed, copy })}</>;
}
