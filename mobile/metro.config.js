// Metro: NativeWind + the shared/ layer via the node_modules/pmsshared symlink.
// Watch the repo root (the symlink target lives there) and resolve bare deps from
// mobile/node_modules (shared/ has none of its own).
const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const path = require("path");

const projectRoot = __dirname;
const repoRoot = path.resolve(projectRoot, "..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [repoRoot];
config.resolver.nodeModulesPaths = [path.resolve(projectRoot, "node_modules")];
config.resolver.unstable_enableSymlinks = true;

module.exports = withNativeWind(config, { input: "./src/global.css" });
