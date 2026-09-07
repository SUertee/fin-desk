import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { AuthGate } from "./auth";
import { I18nProvider } from "./i18n";
import "./index.css";
import "./product.css";
import "./mobile.css";
import "./auth.css";

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <AuthGate>
      <App />
    </AuthGate>
  </I18nProvider>
);
