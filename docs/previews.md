# Previews

Previews are read-only and bounded. Expensive work runs in Textual worker
threads so navigation, search and resizing remain responsive. A slow, outdated
preview cannot replace a newer selection.

## Preview types

| Selection | Preview |
| --- | --- |
| Directory | Entry counts and an open instruction; contents are not recursively sized |
| Image | Pillow metadata plus Chafa ANSI symbols, or a Pillow ASCII fallback |
| Video | Duration, resolution, codec, container, bitrate and a cached still frame |
| PDF | Text from the first three pages plus an optional first-page thumbnail |
| Markdown | Bounded UTF-8 text rendered as Markdown |
| Text / code | Bounded UTF-8 source text |
| Other | Metadata and a note that the file remains available to external tools |

Video previews are still images. Only `mpv` performs real playback.

## Images

Chafa renders the image into ANSI symbols that can be embedded in the terminal
interface without Kitty Graphics or Sixel support. PewwTerm requests symbol
output with terminal probing disabled. Chafa's default probing can consume
capability replies as keyboard input, which is especially visible under tmux.

When Chafa is missing, fails or produces no output, PewwTerm uses a monochrome
Pillow ASCII fallback. Corrupt or unsupported images report the decoder error
instead of raising into the event loop.

## Video

`ffprobe` supplies metadata from the first video stream and the container. A
still frame near the first second is extracted with `ffmpeg`; very short videos
are retried at timestamp zero. The frame is scaled for the preview panel and
rendered with the same Chafa or Pillow path as images.

Thumbnails are stored atomically: FFmpeg writes a temporary `.part.jpg` file and
the cache entry is renamed only after a successful, non-empty result.

## PDF

`pdftotext` extracts text from the first three pages. An optional first-page
thumbnail is rendered by `pdftoppm` and then sent through the image renderer.
When Poppler is missing or a PDF is encrypted/corrupt, the preview reports the
problem and keeps whatever information is available.

## Text, Markdown and binary files

Text is read with a byte and line limit. Decode errors are replaced rather than
raised, but content that contains a NUL byte in the sampled prefix is treated as
binary and labelled instead of being dumped as mojibake. Files without a
built-in preview show metadata and a note that external tools can open them.

## Cache

Generated video frames and PDF thumbnails are cached under:

```text
$PEWWTERM_CACHE_DIR            # if set
$XDG_CACHE_HOME/pewwterm       # otherwise
~/.cache/pewwterm              # default
```

If the default home cache is not writable, PewwTerm falls back to the system
temporary directory. An explicit override is honoured as written. The cache key
includes the resolved path, file size and modification timestamp, so replacing a
file invalidates its old preview.

## Safety limits

External preview calls use argument lists, never a shell, capture output, use
`check=False` and apply a 20-second timeout. Text and PDF output is bounded.
Recursive traversal is bounded by depth and result count. Missing optional tools
degrade the preview instead of crashing the application. `mpv` playback is the
exception: it runs interactively while the terminal is suspended, so its output
is not captured and playback is not time-limited.
