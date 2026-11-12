#!/usr/bin/env node
// 离线模拟 Verge 运行全局 Script.js，只打印 proxy-providers / 固定组 / listeners 的结构。
// 用法：
//   node simulate.js <Script.js>                 打印该脚本对内置脱敏示例配置的输出
//   node simulate.js <Script.js> <config.json>   用自定义 JSON 示例配置（不要用含密钥的真实配置）
//   node simulate.js --compare <a.js> <b.js>     比较两个脚本的效果（按名字排序后比较）
// 不打印 proxies 列表内容，即使示例里有也不会输出。
"use strict";
const fs = require("fs");
const vm = require("vm");

function sampleConfig() {
  return {
    "mixed-port": 7897,
    proxies: [{ name: "PROFILE-NODE", type: "vless", server: "203.0.113.10", port: 443, uuid: "00000000-0000-0000-0000-000000000000" }],
    "proxy-groups": [
      { name: "节点选择", type: "select", proxies: ["PROFILE-NODE", "DIRECT"] },
      { name: "固定美国", type: "select", proxies: ["DIRECT"] }, // 旧的同名组，应被替换
    ],
    "proxy-providers": { "airport": { type: "http", url: "https://example.invalid/sub", path: "./proxies/airport.yaml" } },
    listeners: [{ name: "other-in", type: "socks", listen: "127.0.0.1", port: 7999, proxy: "DIRECT" }],
    rules: ["MATCH,节点选择"],
  };
}

function run(scriptPath, cfg) {
  const code = fs.readFileSync(scriptPath, "utf8");
  const ctx = vm.createContext({ console });
  const main = new vm.Script(code + "\n;main", { filename: scriptPath }).runInContext(ctx);
  if (typeof main !== "function") throw new Error("script has no main()");
  return JSON.parse(JSON.stringify(main(JSON.parse(JSON.stringify(cfg)), "sample-profile")));
}

function summary(out) {
  const byName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  const providers = {};
  for (const k of Object.keys(out["proxy-providers"] || {}).sort()) providers[k] = out["proxy-providers"][k];
  return {
    "proxy-providers": providers,
    "proxy-groups": (out["proxy-groups"] || []).map(g => ({ name: g.name, type: g.type, use: g.use, proxies: g.proxies })).sort(byName),
    listeners: (out.listeners || []).slice().sort(byName),
    proxiesCount: (out.proxies || []).length,
    rules: out.rules,
  };
}

const args = process.argv.slice(2);
if (args[0] === "--compare") {
  const cfg = args[3] ? JSON.parse(fs.readFileSync(args[3], "utf8")) : sampleConfig();
  const a = JSON.stringify(summary(run(args[1], cfg)), null, 2);
  const b = JSON.stringify(summary(run(args[2], cfg)), null, 2);
  if (a === b) { console.log("EQUIVALENT"); process.exit(0); }
  console.log("DIFFERENT\n--- " + args[1] + "\n" + a + "\n--- " + args[2] + "\n" + b);
  process.exit(1);
} else if (args[0]) {
  const cfg = args[1] ? JSON.parse(fs.readFileSync(args[1], "utf8")) : sampleConfig();
  console.log(JSON.stringify(summary(run(args[0], cfg)), null, 2));
} else {
  console.error("usage: node simulate.js <Script.js> [config.json] | --compare <a.js> <b.js> [config.json]");
  process.exit(2);
}
