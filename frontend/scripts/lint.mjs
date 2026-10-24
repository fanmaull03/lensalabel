import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { transform } from "esbuild";

const roots = ["src", "scripts"];
const files = [];
function collect(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) collect(path);
    else if (/\.(js|jsx|mjs)$/.test(entry.name)) files.push(path);
  }
}
for (const root of roots) collect(root);

const errors = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  try {
    await transform(source, { loader: file.endsWith(".jsx") ? "jsx" : "js", sourcefile: file });
  } catch (error) {
    errors.push(`${relative(".", file)}: ${error.message}`);
  }
}
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`lint lulus: sintaks ${files.length} berkas JS/JSX diperiksa dengan esbuild.`);
}
