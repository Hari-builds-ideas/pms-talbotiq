// Metro: NativeWind + the shared/ layer (outside mobile/) resolved via a custom
// resolveRequest that maps "@shared[/sub]" → <repo>/shared/src[/sub] and returns
// the source file directly (robust on-device; no symlink). The repo root is a
// watchFolder so Metro serves shared/, and bare deps (axios) resolve from
// mobile/node_modules since shared/ has none of its own.
const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const path = require("path");
const fs = require("fs");

const projectRoot = __dirname;
const repoRoot = path.resolve(projectRoot, "..");
const sharedSrc = path.resolve(repoRoot, "shared/src");
const EXTS = [".ts", ".tsx", ".js", ".jsx", ".json"];

function resolveShared(sub) {
  const base = path.join(sharedSrc, sub);
  for (const ext of EXTS) if (fs.existsSync(base + ext)) return base + ext;
  for (const ext of EXTS) {
    const idx = path.join(base, "index" + ext);
    if (fs.existsSync(idx)) return idx;
  }
  return null;
}

const config = getDefaultConfig(projectRoot);

config.watchFolders = [repoRoot];
config.resolver.nodeModulesPaths = [path.resolve(projectRoot, "node_modules")];

const upstreamResolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "@shared" || moduleName.startsWith("@shared/")) {
    const sub = moduleName === "@shared" ? "" : moduleName.slice("@shared/".length);
    const filePath = resolveShared(sub);
    if (filePath) return { type: "sourceFile", filePath };
  }
  return (upstreamResolveRequest ?? context.resolveRequest)(context, moduleName, platform);
};

module.exports = withNativeWind(config, { input: "./src/global.css" });
