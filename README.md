# iptv-ir

A clean, verified Iranian IPTV playlist for TV boxes, rebuilt daily.

**Playlist URL** — point any player at this:

```
https://raw.githubusercontent.com/aghamorad/iptv-ir/main/ir.m3u
```

## What this is

Upstream is [Free-TV/IPTV](https://github.com/Free-TV/IPTV), whose Iran list is
official IRIB channels on the domestic telewebion CDN — so they work inside Iran
with no VPN. It is not usable on a TV box as shipped, for three reasons:

- several entries are dead: an expired TLS certificate, a hostname that no
  longer resolves, or a master manifest whose every rendition 404s;
- `tvg-chno` repeats, so the box's own numbering contradicts itself;
- the `x-tvg-url` header lists ~100 EPG feeds copied across all 98 country
  lists, and none of them cover these channels.

`build.py` rebuilds the list daily: known-dead entries are repointed at a
working host or dropped, survivors are renumbered `1..N` in the source's order,
and the header is written plain.

## Why the checks are the interesting part

A `200` on a master manifest proves nothing. `live.presstv.co.uk` answers `200`
with a valid `#EXTM3U` while **every** rendition underneath is a `404`, which is
exactly the kind of entry that shows up on a TV as a channel that never loads.
So every candidate is checked by resolving redirects, walking to a rendition,
and downloading an actual media segment:

```
master 200 -> rendition 200 -> segment 200  = kept
master 200 -> rendition 404                 = dropped
```

Redirects are resolved at every hop because telewebion serves a per-request
load-balancer host, and segment URLs are only valid against the host that
served the playlist.

And a stream that plays under macOS `curl` proves nothing either. `live4.presstv.ir`
sends its leaf certificate **without the intermediate**:

```
$ echo | openssl s_client -connect live4.presstv.ir:443 -servername live4.presstv.ir
 0 s:CN=*.presstv.ir
   i:C=CN, O=TrustAsia Technologies, Inc., CN=LiteSSL Pro RSA CA 2025
Verify return code: 21 (unable to verify the first certificate)
```

macOS papers over that from its own system store, so `curl` fetches the manifest
happily and a build run on a Mac keeps the channel. Android does not: the
platform TrustManager performs no AIA fetching and ships no such intermediate, so
the box refuses the stream outright. Checked from Linux, the same URL fails. That
one difference is enough to make a Mac build and a CI build disagree about
whether a channel exists, which is why `chain_complete()` runs `openssl s_client`
before the HTTP probe — it is the closest cheap approximation of the box's own
TLS stack.

## Current state

20 channels, all end-to-end verified. Dropped as unfixable:

| Channel | Why |
| --- | --- |
| Al-Alam | `live2.alalam.ir` certificate expired 2026-08-25 |
| IranPress | `live1.presstv.ir` no longer resolves |
| iFilm 2 / Arabic / English | presstv.co.uk renditions all 404, nothing else carries them |
| Press TV French | `live4.presstv.ir` sends no intermediate certificate, and no other host carries the feed |

Press TV, iFilm and IRINN are repointed at telewebion: the upstream
`presstv.co.uk` and plain-`http` URLs are dead or unreliable, and the same
channels are served domestically over TLS. Nothing in the list is plain `http`,
so Android's cleartext policy is never a factor.

## Running it yourself

```bash
python3 build.py     # writes ir.m3u, exits non-zero if too few channels survive
```

No dependencies beyond `python3`, `curl` and `openssl`. The GitHub Action runs it
daily at 00:50 UTC and commits `ir.m3u` when the result changes.
