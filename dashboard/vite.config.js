import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function silenceProxyErrors(proxy) {
  proxy.on("error", (err) => {
    if (err.code === "ECONNREFUSED") return;
    console.error(err);
  });
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/state": { target: "http://127.0.0.1:8000", configure: silenceProxyErrors },
      "/control": { target: "http://127.0.0.1:8000", configure: silenceProxyErrors },
      "/benchmark": { target: "http://127.0.0.1:8000", configure: silenceProxyErrors },
    },
  },
});
