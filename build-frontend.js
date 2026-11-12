/*
 * Compiles frontend-src/app.jsx to wwwroot/assets/app.js and copies the
 * stylesheet across.
 *
 * There is no build pipeline, no bundler and no node_modules in the project —
 * the website is plain React served from wwwroot. This script exists only to
 * turn JSX into the plain JavaScript the browser loads.
 *
 * Usage (from the project root):
 *
 *     npm install @babel/standalone
 *     node build-frontend.js
 *
 * Then refresh the browser. If the server is already running there is no need
 * to restart it — wwwroot is served from disk.
 */

const fs = require("fs");
const path = require("path");

let Babel;
try {
  Babel = require("@babel/standalone");
} catch {
  console.error("@babel/standalone is not installed. Run:\n\n  npm install @babel/standalone\n");
  process.exit(1);
}

const root  = __dirname;
const jsx   = path.join(root, "frontend-src", "app.jsx");
const css   = path.join(root, "frontend-src", "style.css");
const outJs = path.join(root, "backend", "DailyWork.Api", "wwwroot", "assets", "app.js");
const outCss= path.join(root, "backend", "DailyWork.Api", "wwwroot", "assets", "style.css");

const source = fs.readFileSync(jsx, "utf8");

let code;
try {
  code = Babel.transform(source, { presets: ["react"] }).code;
} catch (err) {
  // A JSX syntax error is reported with its line and column, which is the
  // single most useful thing when a change breaks the page.
  console.error("\nJSX did not compile:\n");
  console.error(err.message);
  process.exit(1);
}

fs.writeFileSync(outJs, code);
fs.copyFileSync(css, outCss);

console.log("app.js   " + code.length.toLocaleString() + " bytes written");
console.log("style.css copied");
console.log("\nRefresh the browser (Ctrl+F5) to pick up the change.");
