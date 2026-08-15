import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import AdminDashboard from "./pages/AdminDashboard";
import AdminExceptionDetail from "./pages/AdminExceptionDetail";
import AdminCreateShipment from "./pages/AdminCreateShipment";
import AdminSlotManager from "./pages/AdminSlotManager";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/exceptions/:exceptionId" element={<AdminExceptionDetail />} />
        <Route path="/admin/shipments/new" element={<AdminCreateShipment />} />
        <Route path="/admin/slots" element={<AdminSlotManager />} />
        <Route path="/*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
