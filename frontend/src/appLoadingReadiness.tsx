import { useEffect, useRef } from "react";
import { useIsFetching } from "@tanstack/react-query";

import { queryClient } from "./apiClientContext";

export function RouteSuspenseFallback({
  setRouteSuspensePending,
}: {
  setRouteSuspensePending: (isPending: boolean) => void;
}) {
  useEffect(() => {
    setRouteSuspensePending(true);
    return () => setRouteSuspensePending(false);
  }, [setRouteSuspensePending]);

  return <p className="status status-neutral">Loading view...</p>;
}

export function useAppLoadingReadiness(locationPathname: string, routeSuspensePending: boolean) {
  const activeFetchCount = useIsFetching();
  const previousLocationPathname = useRef<string | null>(null);
  const readyTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (previousLocationPathname.current === null) {
      previousLocationPathname.current = locationPathname;
      return;
    }
    if (previousLocationPathname.current !== locationPathname) {
      previousLocationPathname.current = locationPathname;
      window.__cpwAppLoadingBegin?.();
    }
  }, [locationPathname]);

  useEffect(() => {
    if (readyTimerRef.current !== null) {
      window.clearTimeout(readyTimerRef.current);
      readyTimerRef.current = null;
    }

    if (activeFetchCount > 0 || routeSuspensePending) {
      return undefined;
    }

    readyTimerRef.current = window.setTimeout(() => {
      if (queryClient.isFetching() === 0) {
        window.__cpwAppLoadingReady?.();
      }
      readyTimerRef.current = null;
    }, 180);

    return () => {
      if (readyTimerRef.current !== null) {
        window.clearTimeout(readyTimerRef.current);
        readyTimerRef.current = null;
      }
    };
  }, [activeFetchCount, locationPathname, routeSuspensePending]);
}
