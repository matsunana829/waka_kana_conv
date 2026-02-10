import re
import os
from typing import Optional

import MeCab


_KATAKANA_RE = re.compile(r"^[\u30A1-\u30FA\u30FC]+$")


def _kata_to_hira(text: str) -> str:
    # Convert katakana to hiragana; leave other chars as-is.
    result = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def _pick_reading(feature: str, surface: str) -> str:
    parts = feature.split(",")
    # Heuristic: choose the first katakana-like field that is not "*".
    for part in parts:
        if part != "*" and _KATAKANA_RE.match(part):
            return part
    return surface


def _default_mecabrc() -> Optional[str]:
    env = os.environ.get("MECABRC")
    if env:
        return env
    candidates = [
        r"C:\Program Files\MeCab\etc\mecabrc",
        r"C:\Program Files (x86)\MeCab\etc\mecabrc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def create_tagger(dic_dir: Optional[str], mecabrc_path: Optional[str] = None) -> MeCab.Tagger:
    args = []
    mecabrc = mecabrc_path or _default_mecabrc()
    if mecabrc:
        args.append(f'-r "{mecabrc}"')
    if dic_dir:
        args.append(f'-d "{dic_dir}"')
    return MeCab.Tagger(" ".join(args))


def convert_text(text: str, tagger: MeCab.Tagger) -> str:
    # MeCab returns a string with "surface\tfeature" lines, ending with "EOS".
    parsed = tagger.parse(text)
    if parsed is None:
        return text

    out = []
    for line in parsed.splitlines():
        if line == "EOS" or not line:
            continue
        if "\t" not in line:
            out.append(line)
            continue
        surface, feature = line.split("\t", 1)
        reading = _pick_reading(feature, surface)
        out.append(reading)

    return _kata_to_hira("".join(out))
