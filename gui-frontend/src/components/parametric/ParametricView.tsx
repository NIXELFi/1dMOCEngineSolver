import { useEffect } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import ParametricSetupForm from "./ParametricSetupForm";
import ParametricRunGrid from "./ParametricRunGrid";
import ParametricResultsView from "./ParametricResultsView";

/**
 * Root component for the Parametric tab. Routes between three modes
 * based on the store state:
 *  - Mode A (setup): no current study
 *  - Mode B (running): current study status is "running"
 *  - Mode C (results): current study status is "complete"/"stopped"/"error"
 */
export default function ParametricView() {
  const current = useParametricStore((s) => s.current);
  const parametersLoaded = useParametricStore((s) => s.parametersLoaded);
  const setAvailableParameters = useParametricStore(
    (s) => s.setAvailableParameters,
  );
  const setStudies = useParametricStore((s) => s.setStudies);
  const setStudiesLoading = useParametricStore((s) => s.setStudiesLoading);
  const setStudiesError = useParametricStore((s) => s.setStudiesError);

  // Load sweepable parameters once
  useEffect(() => {
    if (parametersLoaded) return;
    let cancelled = false;
    api
      .listParametricParameters()
      .then((params) => {
        if (!cancelled) setAvailableParameters(params);
      })
      .catch((err) => {
        console.error("failed to load parametric parameters", err);
      });
    return () => {
      cancelled = true;
    };
  }, [parametersLoaded, setAvailableParameters]);

  // Load past studies on mount
  useEffect(() => {
    setStudiesLoading(true);
    api
      .listParametricStudies()
      .then((studies) => setStudies(studies))
      .catch((err) => setStudiesError(String(err)))
      .finally(() => setStudiesLoading(false));
  }, [setStudies, setStudiesLoading, setStudiesError]);

  let content: React.ReactNode;
  if (current === null) {
    content = <ParametricSetupForm />;
  } else if (current.status === "running") {
    content = <ParametricRunGrid />;
  } else {
    content = <ParametricResultsView />;
  }

  return <div className="flex-1 overflow-hidden">{content}</div>;
}
