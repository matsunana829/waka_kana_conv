import re
import os
from typing import Optional

import MeCab


# カタカナ/ひらがな判定用の正規表現
_KATAKANA_RE = re.compile(r"^[\u30A1-\u30FA\u30FC]+$")
_HIRAGANA_RE = re.compile(r"^[\u3041-\u3096\u309D\u309E]+$")


def _kata_to_hira(text: str) -> str:
    # カタカナをひらがなに変換（それ以外は保持）
    result = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def _hira_to_kata(text: str) -> str:
    # ひらがなをカタカナに変換（それ以外は保持）
    result = []
    for ch in text:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            result.append(chr(code + 0x60))
        else:
            result.append(ch)
    return "".join(result)


def _pick_reading(feature: str, surface: str) -> str:
    # -Fで「表層\t読み」形式にしているため、featureが読みになっている想定
    if not feature or feature == "*" or feature == surface:
        return surface
    return feature


def _dakuten_map() -> dict[str, str]:
    return {
        "か": "が",
        "き": "ぎ",
        "く": "ぐ",
        "け": "げ",
        "こ": "ご",
        "さ": "ざ",
        "し": "じ",
        "す": "ず",
        "せ": "ぜ",
        "そ": "ぞ",
        "た": "だ",
        "ち": "ぢ",
        "つ": "づ",
        "て": "で",
        "と": "ど",
        "は": "ば",
        "ひ": "び",
        "ふ": "ぶ",
        "へ": "べ",
        "ほ": "ぼ",
        "う": "ゔ",
        "カ": "ガ",
        "キ": "ギ",
        "ク": "グ",
        "ケ": "ゲ",
        "コ": "ゴ",
        "サ": "ザ",
        "シ": "ジ",
        "ス": "ズ",
        "セ": "ゼ",
        "ソ": "ゾ",
        "タ": "ダ",
        "チ": "ヂ",
        "ツ": "ヅ",
        "テ": "デ",
        "ト": "ド",
        "ハ": "バ",
        "ヒ": "ビ",
        "フ": "ブ",
        "ヘ": "ベ",
        "ホ": "ボ",
        "ウ": "ヴ",
    }


def _expand_odoriji(text: str) -> str:
    # かな変換後の踊り字展開（ゝゞヽヾの残りを処理）
    dakuten = _dakuten_map()
    result = []
    prev = ""
    for ch in text:
        if ch in ("ゝ", "ヽ"):
            result.append(prev if prev else ch)
        elif ch in ("ゞ", "ヾ"):
            result.append(dakuten.get(prev, prev if prev else ch))
        else:
            result.append(ch)
            prev = ch
    return "".join(result)


def _is_hiragana(ch: str) -> bool:
    return bool(_HIRAGANA_RE.match(ch))


def _pre_expand_odoriji(text: str) -> str:
    # MeCab前の踊り字展開（前の文字がひらがなの場合のみ）
    dakuten = _dakuten_map()
    result = []
    prev = ""
    for ch in text:
        if ch in ("ゝ", "ヽ"):
            result.append(prev if _is_hiragana(prev) else ch)
            continue
        if ch in ("ゞ", "ヾ"):
            if _is_hiragana(prev):
                result.append(dakuten.get(prev, prev))
            else:
                result.append(ch)
            continue
        result.append(ch)
        prev = ch
    return "".join(result)


def _default_mecabrc() -> Optional[str]:
    env = os.environ.get("MECABRC")
    if env:
        return env
    candidates = [
        r"C:\Program Files\MeCab\etc\mecabrc",
        r"C:\Program Files (x86)\MeCab\etc\mecabrc",
        "/etc/mecabrc",
        "/usr/local/etc/mecabrc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def create_tagger(
    dic_dir: Optional[str],
    mecabrc_path: Optional[str] = None,
    reading_field: int = 9,
) -> MeCab.Tagger:
    args = []
    mecabrc = mecabrc_path or _default_mecabrc()
    if mecabrc:
        args.append(f'-r "{mecabrc}"')
    if dic_dir:
        args.append(f'-d "{dic_dir}"')
    # UniDic Waka: 指定された読みフィールドを使う（既定は %f[9]）
    args.append(f'-F "%m\\t%f[{reading_field}]\\n"')
    args.append('-U "%m\\t%m\\n"')
    args.append('-E "EOS\\n"')
    return MeCab.Tagger(" ".join(args))


def convert_text(
    text: str,
    tagger: MeCab.Tagger,
    expand_odoriji: bool = False,
    output_mode: str = "hiragana",
) -> str:
    # 形態素解析の前に踊り字を簡易展開（有効時のみ）
    if expand_odoriji:
        text = _pre_expand_odoriji(text)

    # MeCabの出力は「表層\t読み」形式（EOSで終わる）
    parsed = tagger.parse(text)
    if parsed is None:
        return text

    out = []
    prev_reading = ""
    for line in parsed.splitlines():
        if line == "EOS" or not line:
            continue
        if "\t" not in line:
            out.append(line)
            continue
        surface, feature = line.split("\t", 1)
        # 〳〵は直前の形態素読みを繰り返す
        if surface == "〳〵" and prev_reading:
            out.append(prev_reading)
            continue
        reading = _pick_reading(feature, surface)
        out.append(reading)
        prev_reading = reading

    hira = _kata_to_hira("".join(out))
    if expand_odoriji:
        # かな化後に残った踊り字を展開
        hira = _expand_odoriji(hira)
    if output_mode == "katakana":
        return _hira_to_kata(hira)
    return hira
