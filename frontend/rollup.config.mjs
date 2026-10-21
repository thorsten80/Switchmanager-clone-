import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

const production = !process.env.ROLLUP_WATCH;

export default {
  input: "src/switch-manager-panel.ts",
  output: {
    file: "../custom_components/switch_manager/assets/switch_manager_panel.js",
    format: "es",
    inlineDynamicImports: true,
    sourcemap: !production,
  },
  plugins: [
    typescript({ noEmit: false, outDir: "../custom_components/switch_manager/assets" }),
    resolve(),
    production && terser({ format: { comments: false } }),
  ],
};
