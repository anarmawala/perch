import { useEffect, useRef, useState } from "preact/hooks";

/** Poll an async function on an interval; returns the latest value (or null). */
export function usePoll<T>(fn: () => Promise<T>, ms: number): T | null {
  const [value, setValue] = useState<T | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const v = await fnRef.current();
        if (alive) setValue(v);
      } catch {
        /* transient network errors are fine; keep last value */
      }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [ms]);

  return value;
}

export type Route = "live" | "timeline" | "settings";

/** Minimal hash router: #/ , #/timeline , #/settings */
export function useHashRoute(): [Route, (r: Route) => void] {
  const parse = (): Route => {
    const h = location.hash.replace(/^#\/?/, "");
    return h === "timeline" || h === "settings" ? h : "live";
  };
  const [route, setRoute] = useState<Route>(parse());
  useEffect(() => {
    const onHash = () => setRoute(parse());
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const navigate = (r: Route) => {
    location.hash = r === "live" ? "/" : `/${r}`;
  };
  return [route, navigate];
}
