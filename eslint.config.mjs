import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", "desktop/node_modules/**", "src/gui/web/vendor/**"] },
  js.configs.recommended,
  {
    // src/gui/web/*.js are browser scripts loaded by <script>, not modules.
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: globals.browser,
    },
  },
  {
    // The Electron main process and its preload run under Node.
    files: ["desktop/main.js", "desktop/preload.js"],
    languageOptions: {
      sourceType: "commonjs",
      globals: globals.node,
    },
  },
];
