#!/bin/sh
# Read-only check of Reality destination candidates from the VPS itself.
# For every candidate and every available stack, require TLS 1.3 + ALPN h2 and report handshake time.
# Usage: sh check-dest.sh [-4] [-6] host1 [host2 ...]
#   default candidates: www.amd.com (default target) www.apple.com www.cloudflare.com www.bing.com
# Exit 0 if at least one candidate passed on every requested stack.

fams=""
while [ $# -gt 0 ]; do
  case "$1" in -4) fams="$fams 4" ;; -6) fams="$fams 6" ;; *) break ;; esac
  shift
done
[ -z "$fams" ] && fams="4 6"
[ $# -eq 0 ] && set -- www.amd.com www.apple.com www.cloudflare.com www.bing.com
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 2; }
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'

any_ok=1
for host in "$@"; do
  host_ok=0
  for f in $fams; do
    # Browser UA: CDN bot filters (Akamai on www.amd.com) reset curl's HTTP/2 stream after a perfect
    # TLS 1.3 + h2 handshake, which gives code=000. Reality only needs the handshake, so judge on it.
    out=$(curl "-$f" -sv --tlsv1.3 --http2 -o /dev/null -m 10 -A "$UA" -H 'Accept: text/html' \
          -w 'appconnect=%{time_appconnect} http=%{http_version} code=%{http_code}\n' \
          "https://$host/" 2>&1)
    tls13=no; h2=no
    echo "$out" | grep -Eq 'SSL connection using TLSv1\.3|TLSv1\.3 \(IN\)' && tls13=yes
    echo "$out" | grep -Eiq 'ALPN.*(accepted|server accepted).*h2|http=2' && h2=yes
    stat=$(echo "$out" | grep -E '^appconnect=' | tail -n1)
    if [ -z "$stat" ] || echo "$stat" | grep -Eq 'appconnect=0(\.0+)? '; then
      echo "$host v$f: UNREACHABLE"
      host_ok=1
    elif [ "$tls13" = yes ] && [ "$h2" = yes ]; then
      echo "$host v$f: OK tls1.3+h2 $stat"
    else
      echo "$host v$f: FAIL tls1.3=$tls13 h2=$h2 $stat"
      host_ok=1
    fi
  done
  [ "$host_ok" = 0 ] && any_ok=0
done
[ "$any_ok" = 0 ] && echo "RESULT: at least one candidate passed on all requested stacks" || echo "RESULT: no candidate passed on all requested stacks"
exit $any_ok
