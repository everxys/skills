# 记账后端端到端探针（不开 Tauri GUI）

目的：在不启动桌面应用的前提下，确认“只抓启用币种”“设置键迁移”“MCP 工具增删”这类后端行为真的成立。`src-tauri/src/bin/accounting_mcp.rs` 是记账的 MCP 入口，用 stdio 传 JSON-RPC，一行一个 JSON 对象。

## 步骤

1. 先编译 bin：

```bash
cd /c/Users/everx/dev/toolbox
cargo build --manifest-path src-tauri/Cargo.toml --bin accounting_mcp --locked
```

2. 用临时库跑一次 `refresh_rates`，让 bin 自己建表（不要手写 DDL，schema 会漂移）：

```bash
DB="$LOCALAPPDATA/Temp/acct-probe.db"; rm -f "$DB" "$DB-wal" "$DB-shm"
WDB=$(cygpath -w "$DB")   # MSYS 路径必须转成原生路径再喂给原生 exe/python
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"refresh_rates","arguments":{"force":true}}}' \
  | ./src-tauri/target/debug/accounting_mcp.exe --db "$WDB"
```

3. 用 python 改设置 + 造数据（第一步已经建好表）：

```python
import sqlite3
c = sqlite3.connect(r"C:\Users\everx\AppData\Local\Temp\acct-probe.db")
c.execute("INSERT OR REPLACE INTO accounting_settings(key,value) VALUES('enabled_currencies','[\"CNY\",\"USD\",\"BTC\"]')")
c.commit()
```

想测旧键迁移，就改成只写 `tracked_currencies` 旧键，再跑一次 `set_base_currency`/`refresh_rates`，最后查 `accounting_settings` 看新键是否写回、旧键是否删除。

4. 再跑一轮并把结果与落库一起打出来：

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"refresh_rates","arguments":{"force":true}}}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_balances","arguments":{}}}' \
 | ./src-tauri/target/debug/accounting_mcp.exe --db "$WDB" 2>/dev/null \
 | python -c "import json,sys
for line in sys.stdin:
    r=json.loads(line)['result']
    print([t['name'] for t in r['tools']] if 'tools' in r else r['content'][0]['text'].splitlines()[0])"
python -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print(c.execute('select currency,round(price_in_usd,4),source from accounting_rates order by currency').fetchall());print(c.execute('select key,value from accounting_settings order by key').fetchall())" "$WDB"
```

## 判读

- `accounting_rates` 的行集合 === 启用币种集合（+ 主币种），就是“只跟踪启用币种”成立。
- `tools/list` 里没有刚删掉的工具，才算删干净（`set_rate` 这类旁路工具常被忘在 MCP 层）。
- `accounting_settings` 里只应留下新键；旧键还在说明迁移没写回。
- 收尾删掉临时库（连 `-wal`/`-shm`）：`rm -f "$DB" "$DB-wal" "$DB-shm"`。

## 注意

- 探针用的是临时库，**不要**指向 `toolbox.db`（用户真实账本）。
- 网络抓取会打到真实汇率源（crypto 走 OKX/Binance，法币走公开源）；只想测逻辑时优先断言“落库集合”，不要断言具体价格。
