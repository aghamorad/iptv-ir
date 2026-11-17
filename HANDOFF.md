# HANDOFF — iptv-ir

## Objective

A verified Iranian IPTV playlist for the Mi Box 4 in the living room, rebuilt
without a human in the loop. Source of truth is Free-TV/IPTV's Iran list.

## Where things stand

* `build.py` rebuilds `ir.m3u` from Free-TV/IPTV, repoints or drops known-dead
  entries, renumbers `tvg-chno` 1..N, and verifies every survivor end to end.
* `ir.m3u` is live at
  `https://raw.githubusercontent.com/aghamorad/iptv-ir/main/ir.m3u` — **20
  channels**. The GitHub Action rebuilds daily at 00:50 UTC.
* The box (`192.168.1.45`, Mi Box 4, Android 9) is configured against that URL
  and loads it: MyTV's own log reports
  `加载订阅源（Iran TV (verified)）：1个分组，20个频道` — "1 group, 20 channels".

## Decisions and why

* **Two checks, not one.** A master manifest returning 200 can still have every
  rendition 404 (`live.presstv.co.uk`, still true 2026-11-17), and a URL that
  verifies under macOS curl can still be refused by Android
  (`live4.presstv.ir`, which sends no intermediate certificate — openssl reports
  return code 21). `probe()` checks the chain the way the box does *and*
  downloads a media segment.
* **Press TV French is dropped, not kept.** No other host carries the feed
  (telewebion 404s on `presstvfr`), and iptv-org lists only the broken URL.
  Because the drop is automatic, the channel returns by itself if the CDN ever
  fixes its chain.
* **No EPG.** The upstream `x-tvg-url` header lists ~100 epgshare01 feeds copied
  across all 98 country lists and none cover IRIB, so the header is plain.
* **Everything is HTTPS.** Android 9 blocks cleartext by default; nothing in the
  list is `http://`, so that never bites.
* **`FLOOR = 15`.** The build refuses to overwrite a working playlist with a
  wrecked one.

## Verified

* 19 of the 20 channels pull real h264 video from this Mac, on the same network
  as the box, via `ffprobe` (2026-11-17). All 20 are `ncdn.telewebion.ir`.
* The box fetched the playlist in 486 ms and parsed it — raw.githubusercontent.com
  resolves to 185.199.110.133 at ~74 ms from the box's own network, so the
  hosting choice is not a problem from Iran.
* The GitHub Action is green and its output is byte-identical to a local build.

## Open issues

* `ffprobe` on this Mac cannot verify `live4.presstv.ir` (no CA bundle for
  TrustAsia in the Homebrew OpenSSL build). `curl` can. Irrelevant now that the
  channel is dropped, but do not read an ffprobe TLS error there as new.
* The daily Action runs from GitHub's network, not from Iran. Nothing has been
  dropped for that reason so far, but a channel that is geo-restricted to Iran
  would be dropped by CI and stay dropped. If a channel is ever reported missing
  on the box, check the Action log before believing the channel is dead.
* MyTV loads a 787-channel Chinese EPG on every start (~2.6 s). Coverage for
  IRIB is unverified; it may be dead weight, but it was left alone rather than
  disabled on a guess.

## Next concrete action

Nothing pending. If a channel disappears from the TV, run `python3 build.py`
locally and read the per-channel reason it prints.
