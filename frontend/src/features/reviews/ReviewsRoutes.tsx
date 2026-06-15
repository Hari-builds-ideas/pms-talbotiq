import { Route, Routes } from "react-router-dom";
import { ReviewsListPage } from "./ReviewsListPage";
import { ReviewDetailPage } from "./ReviewDetailPage";

/** Reviews sub-routes: list + detail/editor. */
export function ReviewsRoutes() {
  return (
    <Routes>
      <Route index element={<ReviewsListPage />} />
      <Route path=":id" element={<ReviewDetailPage />} />
    </Routes>
  );
}
