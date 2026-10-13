// Limit drawing without replacing the animation clock or its bounded physics steps.
export function createFrameLimiter(fps = 30, hiddenFps = 5) {
  const visibleRate = Math.max(15, Math.min(60, Number(fps) || 30));
  const hiddenRate = Math.max(1, Math.min(15, Number(hiddenFps) || 5));
  let last = -Infinity;
  return {
    fps: visibleRate,
    hiddenFps: hiddenRate,
    due(now, visible) {
      const interval = 1000 / (visible ? visibleRate : hiddenRate);
      if (now - last < interval - 0.5) return false;
      last = now;
      return true;
    }
  };
}
