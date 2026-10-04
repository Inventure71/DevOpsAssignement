// The server owns which room type this launch can create or restore.
export function modeAvailable(ui, mode) {
  return ui.launchStatus === "ready" && ui.launchConfig?.modes[mode]?.enabled === true;
}

export function modeReason(ui, mode) {
  if (ui.launchStatus !== "ready") return "Checking available game modes…";
  return ui.launchConfig.modes[mode]?.reason || "Unavailable in this session.";
}

function validate(config) {
  if (!["demo", "normal"].includes(config?.launch_mode)) return false;
  for (const mode of ["demo", "normal"]) {
    const capability = config.modes?.[mode];
    if (typeof capability?.enabled !== "boolean") return false;
    if (capability.reason !== null && typeof capability.reason !== "string") return false;
    if (config.launch_mode === "demo" && mode === "normal" && capability.enabled) return false;
  }
  return true;
}

export function createLaunchConfig({ ui, api, render }) {
  let pending = null;
  return {
    load() {
      if (pending) return pending;
      ui.launchStatus = "loading";
      ui.launchError = null;
      render();
      pending = (async () => {
        await Promise.resolve();
        try {
          const config = await api("/api/config");
          if (!validate(config)) throw new Error("Invalid game configuration");
          ui.launchConfig = config;
          ui.launchStatus = "ready";
          ui.mode = config.modes[config.launch_mode].enabled
            ? config.launch_mode : config.modes.demo.enabled ? "demo" : config.launch_mode;
          return true;
        } catch {
          ui.launchConfig = null;
          ui.launchStatus = "error";
          ui.launchError = "Couldn’t connect to the game. Try again.";
          return false;
        } finally {
          pending = null;
          render();
        }
      })();
      return pending;
    },
  };
}
