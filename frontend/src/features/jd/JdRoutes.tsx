import { Route, Routes } from "react-router-dom";
import { JdListPage } from "./JdListPage";
import { JdDetailPage } from "./JdDetailPage";

export function JdRoutes() {
  return (
    <Routes>
      <Route index element={<JdListPage />} />
      <Route path=":id" element={<JdDetailPage />} />
    </Routes>
  );
}
