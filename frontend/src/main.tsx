import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProviders } from "@/app/AppProviders";
import "@/styles/globals.css";

const container = document.getElementById("root");

if (!container) {
  throw new Error("Chillify could not mount: the #root container is missing.");
}

createRoot(container).render(
  <StrictMode>
    <AppProviders />
  </StrictMode>,
);
