// ==== clash-fixed-exits (Clash Verge Rev 全局扩展脚本) ===================
// 对所有 profile 生效。本文件不含任何密钥。
// 每个国家一个固定出口端口（绕过规则，和 7897 不同）：
//   127.0.0.1:<port> -> 组 固定<label> -> provider nodes-<code> -> <clash目录>\nodes\<code>.yaml
// 加节点：把节点粘到 nodes\<code>.yaml 的 proxies: 下面，保存，在 Verge「代理」页
//   「代理集合」里刷新 nodes-<code>；节点显示为 固定|<name>。
// 加国家：在下面 FIXED_EXITS 表里加一行，建 nodes\<code>.yaml，再在 Verge 里重新激活当前 profile。
// "./nodes" 是内核 home（服务模式下为 C:\ProgramData\clash-verge-service\users\<sha256(SID)>\runtime）
//   里的 junction，指向 <clash目录>\nodes（服务模式内核只能读 home 内的文件）。

// ---- 配置表：只需要改这里 ------------------------------------------------
const FIXED_EXITS = [
  { code: "tr", label: "土耳其", port: 7901 },
  { code: "us", label: "美国", port: 7902 },
];
const FIXED_PREFIX = "固定|";          // provider 节点名前缀，避免和 profile 自带节点重名
const FIXED_NODES_DIR = "./nodes";      // 相对内核 home
const FIXED_LISTEN = "127.0.0.1";       // 只监听本机回环
const FIXED_HEALTH_CHECK = {
  enable: true,
  url: "https://www.gstatic.com/generate_204",
  interval: 600,
  lazy: false,
};
// ---------------------------------------------------------------------------

function applyFixedExits(config) {
  const providers = Object.assign({}, config["proxy-providers"] || {});
  const groupNames = new Set();
  const listenerNames = new Set();
  const newGroups = [];
  const newListeners = [];

  for (const e of FIXED_EXITS) {
    const providerName = "nodes-" + e.code;
    const groupName = "固定" + e.label;
    const listenerName = "fixed-" + e.code + "-in";
    providers[providerName] = {
      type: "file",
      path: FIXED_NODES_DIR + "/" + e.code + ".yaml",
      "health-check": Object.assign({}, FIXED_HEALTH_CHECK),
      override: { "additional-prefix": FIXED_PREFIX },
    };
    groupNames.add(groupName);
    listenerNames.add(listenerName);
    newGroups.push({ name: groupName, type: "select", use: [providerName] });
    newListeners.push({ name: listenerName, type: "mixed", listen: FIXED_LISTEN, port: e.port, proxy: groupName });
  }

  config["proxy-providers"] = providers;
  config["proxy-groups"] = (config["proxy-groups"] || []).filter(g => !groupNames.has(g.name)).concat(newGroups);
  config.listeners = (config.listeners || []).filter(l => !listenerNames.has(l.name)).concat(newListeners);
  return config;
}

// 如果原来的全局 Script.js 已有 main()，不要整份覆盖：把上面的常量和 applyFixedExits
// 粘进去，并在原 main() 的 return 前加一行 config = applyFixedExits(config);
function main(config, profileName) {
  config = applyFixedExits(config);
  return config;
}
// ==== end clash-fixed-exits ================================================
