"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getGatewayWsUrl, type AgentWsEvent } from "@/lib/gateway";

export type GatewayConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting";

type GatewayWsContextValue = {
  connectionState: GatewayConnectionState;
  subscribe: (fn: (event: AgentWsEvent) => void) => () => void;
};

const GatewayWsContext = createContext<GatewayWsContextValue | null>(null);

export function GatewayWsProvider({ children }: { children: ReactNode }) {
  const [connectionState, setConnectionState] =
    useState<GatewayConnectionState>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef(new Set<(e: AgentWsEvent) => void>());
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const attemptRef = useRef(0);

  const subscribe = useCallback((fn: (e: AgentWsEvent) => void) => {
    listenersRef.current.add(fn);
    return () => {
      listenersRef.current.delete(fn);
    };
  }, []);

  useEffect(() => {
    const url = getGatewayWsUrl();
    intentionalCloseRef.current = false;

    const connect = () => {
      if (intentionalCloseRef.current) return;
      const attempt = attemptRef.current;
      setConnectionState((prev) =>
        prev === "connected" ? prev : attempt === 0 ? "connecting" : "reconnecting"
      );

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnectionState("connected");
      };

      ws.onmessage = (ev) => {
        try {
          const payload = JSON.parse(String(ev.data)) as AgentWsEvent;
          for (const fn of listenersRef.current) {
            try {
              fn(payload);
            } catch {
              /* ignore subscriber */
            }
          }
        } catch {
          /* ignore malformed */
        }
      };

      ws.onerror = () => {
        /* rely on onclose */
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (intentionalCloseRef.current) {
          setConnectionState("disconnected");
          return;
        }
        setConnectionState("disconnected");
        attemptRef.current += 1;
        const delay = Math.min(
          30_000,
          1000 * Math.pow(2, Math.min(attemptRef.current, 5))
        );
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
      setConnectionState("disconnected");
    };
  }, []);

  const value = useMemo(
    () => ({ connectionState, subscribe }),
    [connectionState, subscribe]
  );

  return (
    <GatewayWsContext.Provider value={value}>
      {children}
    </GatewayWsContext.Provider>
  );
}

export function useGatewayWs(): GatewayWsContextValue {
  const ctx = useContext(GatewayWsContext);
  if (!ctx) {
    throw new Error("useGatewayWs must be used within GatewayWsProvider");
  }
  return ctx;
}
