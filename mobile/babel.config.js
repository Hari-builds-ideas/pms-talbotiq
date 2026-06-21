module.exports = function (api) {
  api.cache(true);
  return {
    presets: [
      ["babel-preset-expo", { jsxImportSource: "nativewind" }],
      "nativewind/babel",
    ],
    plugins: [
      // @shared (the source token, same as web) → the "pmsshared" package, which is
      // a symlink in node_modules → ../shared/src (created by the postinstall script).
      // Routing through an in-root node_modules entry is what Metro resolves cleanly.
      ["module-resolver", { alias: { "@shared": "pmsshared" } }],
    ],
  };
};
