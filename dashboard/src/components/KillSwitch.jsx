import { revertToBaseline, resumeAi } from "../api.js";

export default function KillSwitch({ mode, onModeChange }) {
  const isBaseline = mode === "baseline";

  async function toggle() {
    const result = isBaseline ? await resumeAi() : await revertToBaseline();
    onModeChange(result.mode);
  }

  return (
    <button className={`kill-switch${isBaseline ? " active" : ""}`} onClick={toggle}>
      {isBaseline ? "Resume AI Control" : "Revert to Baseline"}
    </button>
  );
}
