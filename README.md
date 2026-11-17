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

## Why the check is the interesting part

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

## Current state

21 channels, all end-to-end verified. Dropped as unfixable:

| Channel | Why |
| --- | --- |
| Al-Alam | `live2.alalam.ir` certificate expired 2026-08-25 |
| IranPress | `live1.presstv.ir` no longer resolves |
| iFilm 2 / Arabic / English | presstv.co.uk renditions all 404, nothing else carries them |

Press TV, iFilm and IRINN are repointed at telewebion: the upstream
`presstv.co.uk` and plain-`http` URLs are dead or unreliable, and the same
channels are served domestically over TLS.

## Running it yourself

```bash
python3 build.py     # writes ir.m3u, exits non-zero if too few channels survive
```

No dependencies beyond `python3` and `curl`. The GitHub Action runs it daily at
00:50 UTC and commits `ir.m3u` when the result changes.
