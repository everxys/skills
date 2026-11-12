# Syncthing REST probes (copy-paste)

All calls assume the local GUI on `127.0.0.1:8384` and `--noproxy '*'` (a host
with Clash/TUN will otherwise hijack loopback).

```bash
CFG="$LOCALAPPDATA/Syncthing"                     # config dir; exe is elsewhere
K=$(grep -o '<apikey>[^<]*' "$CFG/config.xml" | cut -d'>' -f2)
U=http://127.0.0.1:8384
C="curl -s -m 25 --noproxy * -H X-API-Key:$K"
```

## Is this node complete?

```bash
$C "$U/rest/db/status?folder=important" | python -c "import sys,json;d=json.load(sys.stdin);print(d['state'],d['needFiles'],d['needBytes'],d['pullErrors'],float(d['localBytes']))"
```

`needBytes=0` + `state=idle` + `pullErrors=0` = this node is done. Slow on big
folders (30–60 s); do not stack many of these in one shell call.

## Per-device completion

```bash
$C "$U/rest/db/completion?folder=important&device=<DEVICE-ID>"
# -> completion, needBytes, needItems, needDeletes, remoteState
```

`remoteState`: `valid` = peer sent a valid index, `paused` = peer paused the
folder, `notSharing` = peer no longer shares it. A `completion` under 100 with
`needItems: 0` and `needDeletes > 0` is pending deletes, not missing data.

## Real throughput (the only honest "is it slow")

```bash
D="$LOCALAPPDATA/Temp/st"; mkdir -p "$D"
$C $U/rest/system/connections > "$D/a.json"; sleep 20
$C $U/rest/system/connections > "$D/b.json"
python - "$(cygpath -w "$D/a.json")" "$(cygpath -w "$D/b.json")" <<'EOF'
import json,sys
a=json.load(open(sys.argv[1]));b=json.load(open(sys.argv[2]))
for k,v in b['connections'].items():
    p=a['connections'].get(k,{})
    i=v['inBytesTotal']-p.get('inBytesTotal',0); o=v['outBytesTotal']-p.get('outBytesTotal',0)
    print(k[:7], v.get('type'), v.get('isLocal'), v.get('address'), 'in %.2f MB/s out %.2f MB/s'%(i/20e6,o/20e6))
EOF
```

Zero across the board = nothing is moving here; stop tuning this node.

## Did the peer's number just get fresher, or did data really move?

```bash
$C "$U/rest/events?since=0&limit=1000" > "$D/ev.json"   # filter client-side
python - "$(cygpath -w "$D/ev.json")" <<'EOF'
import json,sys,datetime
d=json.load(open(sys.argv[1],encoding='utf-8'))
if isinstance(d,dict): d=d.get('events',[])
prev={}
for e in d:
    if e['type']!='FolderCompletion': continue
    x=e['data']; k=(x['device'][:7],x['folder']); nb=x.get('needBytes',0); t=e['time']
    r=''
    if k in prev:
        dt=(datetime.datetime.fromisoformat(t)-datetime.datetime.fromisoformat(prev[k][0])).total_seconds()
        if dt>0: r='%+.2f MB/s'%((prev[k][1]-nb)/dt/1e6)
    prev[k]=(t,nb)
    print(t[11:19],*k,'%.2f%%'%x.get('completion',0),'need',nb,r)
EOF
```

`need` collapsing by GB in seconds is index catch-up, not a transfer — the
earlier low percentage was stale, not a real deficit.

## Config that decides speed

```bash
$C $U/rest/config/options | python -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ['maxSendKbps','maxRecvKbps','relaysEnabled','localAnnounceEnabled','globalAnnounceEnabled','natEnabled','setLowPriority']})"
$C $U/rest/config/folders | python -c "import sys,json;[print(f['id'],f['type'],[ (d['deviceID'][:7],d.get('paused')) for d in f['devices']]) for f in json.load(sys.stdin)]"
$C $U/rest/config/devices | python -c "import sys,json;[print(d['deviceID'][:7],d['name'],d.get('addresses'),d.get('paused')) for d in json.load(sys.stdin)]"
```

## Log greps that actually answer the question

```bash
CFG="$LOCALAPPDATA/Syncthing"
grep -a "index ID"            "$CFG/syncthing.log" | tail   # peer reset / re-added folder
grep -a "forcibly closed"     "$CFG/syncthing.log" | tail   # peer drops every connection
grep -aE " (WRN|ERR) "        "$CFG/syncthing.log" | tail   # churn, relay, proxy
```

## Host link reality (Windows)

```bash
netsh wlan show interfaces | grep -iE "Name|Radio type|Receive rate|Signal"
netsh interface show interface
ipconfig | grep -B8 "<lan-ip>" | grep -iE "IPv4|adapter|WLAN"
```

Ethernet "Disconnected" while Wi-Fi is "Connected", or a TUN adapter
(`Mihomo`) marked Connected, explains most unexpected throughput numbers before
any Syncthing setting does.
