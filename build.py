#!/usr/bin/env python3
"""Build a clean, verified Iranian IPTV playlist from Free-TV/IPTV.

Free-TV/IPTV's Iran list is the right source: official IRIB channels served from
the domestic telewebion CDN, so they work inside Iran without a VPN. It is not
usable on a TV box as shipped, though:

  * several entries are dead upstream -- an expired TLS certificate, a hostname
    that no longer resolves, or a master manifest whose every rendition 404s;
  * `tvg-chno` repeats, so the box's channel numbering contradicts itself;
  * the `x-tvg-url` header lists ~100 EPG feeds copied across all 98 country
    lists, and none of them carry these channels, so it only costs the player a
    pile of failed downloads.

This rebuilds the list: known-dead entries are repointed at a working host or
dropped, survivors are renumbered 1..N in the source's own order, and each one
is checked by pulling a real media segment. `ir.m3u` is the result.
"""

from __future__ import annotations

import concurrent.futures
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

SOURCE = (
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/"
    "playlists/playlist_iran.m3u8"
)
OUT = "ir.m3u"
HEADER = "#EXTM3U"

# Minimum survivors before we refuse to overwrite a working playlist.
FLOOR = 15

# An HLS tag with its leading '#' missing still shows up in the wild (telewebion
# serves `EXT-X-VERSION:6` bare), so a URI line is anything that is not a tag
# and does not look like `SOMETHING:`.
_TAGLIKE = re.compile(r"^[A-Z0-9-]+:")


def is_uri(line: str) -> bool:
    return bool(line) and not line.startswith("#") and not _TAGLIKE.match(line)


# Where upstream is broken, what to use instead. `None` drops the channel.
OVERRIDES: dict[str, str | None] = {
    # Master manifest is fine but every rendition 404s on presstv.co.uk, and
    # live.presstv.ir no longer resolves. telewebion carries it domestically.
    "Press TV": "https://ncdn.telewebion.ir/presstv/live/playlist.m3u8",
    # Same story: the presstv.co.uk ifilm renditions are gone.
    "iFilm": "https://ncdn.telewebion.ir/ifilm/live/playlist.m3u8",
    # Plain http and an unrelated host; telewebion is the same channel over TLS.
    "IRINN": "https://ncdn.telewebion.ir/irinn/live/playlist.m3u8",
    # live2.alalam.ir's certificate expired 2026-08-25, so any player that
    # validates TLS refuses it, and nothing else carries the channel.
    "Al-Alam News Network Ⓢ": None,
    # live1.presstv.ir no longer resolves.
    "IranPress Ⓢ": None,
    # No working source anywhere for these three.
    "iFilm 2 Ⓢ": None,
    "iFilm Arabic Ⓢ": None,
    "iFilm English Ⓢ": None,
}

ATTR = re.compile(r'([\w-]+)="([^"]*)"')
ATTEMPTS = 2


@dataclass
class Channel:
    name: str
    url: str
    attrs: dict = field(default_factory=dict)


def parse(text: str) -> list[Channel]:
    out: list[Channel] = []
    pending: Channel | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            head, _, name = line.rpartition(",")
            attrs = dict(ATTR.findall(head))
            pending = Channel(name=name.strip() or attrs.get("tvg-name", ""),
                              url="", attrs=attrs)
        elif line.startswith("#"):
            continue
        elif pending is not None:
            pending.url = line
            out.append(pending)
            pending = None
    return out


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "iptv-ir/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _curl(url: str, *, body: bool = True, timeout: int = 25):
    args = ["curl", "-sL", "--max-time", str(timeout)]
    args += ["-o", "-", "-w", "\n%{http_code}\t%{url_effective}"] if body else [
        "-o", "/dev/null", "-w", "%{http_code}\t%{url_effective}"]
    args.append(url)
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 20)
    out = proc.stdout
    payload, _, meta = out.rpartition("\n")
    code, _, eff = meta.partition("\t")
    return code.strip(), eff.strip(), payload


def plays(url: str) -> bool:
    """True only when a real media segment downloads from some rendition.

    A 200 on the master manifest proves nothing: the presstv.co.uk entries
    answered 200 while every rendition underneath was a 404.
    """
    try:
        code, eff, master = _curl(url)
        if code != "200" or not master.lstrip().startswith("#EXTM3U"):
            return False

        lines = master.splitlines()
        renditions: list[tuple[int, str]] = []
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                mm = re.search(r"BANDWIDTH=(\d+)", ln)
                bw = int(mm.group(1)) if mm else 0
                for nxt in lines[i + 1:]:
                    if is_uri(nxt):
                        renditions.append((bw, nxt))
                        break

        if not renditions:
            candidates = [(0, eff, master)]
        else:
            # Highest bitrate first, but one working rendition is enough.
            candidates = []
            for _bw, path in sorted(renditions, reverse=True):
                vurl = urllib.parse.urljoin(eff, path)
                vcode, veff, vbody = _curl(vurl)
                if vcode == "200" and vbody.lstrip().startswith("#EXTM3U"):
                    candidates.append((_bw, veff, vbody))

        for _bw, base, body in candidates:
            seg = next((l for l in body.splitlines() if is_uri(l)), None)
            if not seg:
                continue
            segurl = urllib.parse.urljoin(base, seg)
            scode, _, _ = _curl(segurl, body=False)
            if scode == "200":
                return True
        return False
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def plays_after_retries(url: str) -> bool:
    for attempt in range(ATTEMPTS):
        if plays(url):
            return True
        if attempt + 1 < ATTEMPTS:
            time.sleep(3)
    return False


def main() -> int:
    print(f"source: {SOURCE}")
    channels = parse(fetch(SOURCE))
    print(f"parsed {len(channels)} channels")

    kept: list[Channel] = []
    for ch in channels:
        if ch.name in OVERRIDES:
            replacement = OVERRIDES[ch.name]
            if replacement is None:
                print(f"  drop   {ch.name} (no working source)")
                continue
            print(f"  fix    {ch.name} -> {replacement}")
            ch.url = replacement
        kept.append(ch)

    print(f"probing {len(kept)} channels end to end")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        alive = list(pool.map(lambda c: plays_after_retries(c.url), kept))

    final = []
    for ch, ok in zip(kept, alive):
        if ok:
            final.append(ch)
        else:
            print(f"  drop   {ch.name} (no segment from {ch.url})")

    if len(final) < FLOOR:
        print(f"REFUSING to write: only {len(final)} channels alive", file=sys.stderr)
        return 1

    lines = [HEADER]
    for number, ch in enumerate(final, start=1):
        attrs = dict(ch.attrs)
        attrs["tvg-chno"] = str(number)
        order = ["tvg-id", "tvg-name", "tvg-logo", "tvg-chno", "group-title"]
        rendered = " ".join(f'{k}="{attrs[k]}"' for k in order if attrs.get(k))
        for extra in sorted(set(attrs) - set(order)):
            if extra.startswith("tvg-"):
                continue
            rendered += f' {extra}="{attrs[extra]}"'
        lines.append(f"#EXTINF:-1 {rendered},{ch.name}")
        lines.append(ch.url)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"wrote {OUT}: {len(final)} channels, {len(channels) - len(final)} dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
