import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./games/callbreak"; // register LAKDI UI slots
import "./games/president"; // register President UI slots
import "./games/twentyeight"; // register Twenty-Eight UI slots

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
