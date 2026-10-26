import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Shop from "./Shop";
import Seller from "./Seller";

const isSeller = window.location.pathname.startsWith("/seller");

createRoot(document.getElementById("root")).render(
  <StrictMode>{isSeller ? <Seller /> : <Shop />}</StrictMode>
);
