import io
import os
import ssl
import zipfile
import urllib.request
import urllib.error
from typing import Dict, List, Tuple

import streamlit as st

from io_utils import (
    convert_csv_bytes,
    convert_docx_bytes,
    convert_xml_bytes,
    read_text_bytes,
    texts_to_csv_bytes,
    texts_to_txt_bytes,
    texts_to_xml_bytes,
    write_csv,
)
from mecab_utils import convert_text, create_tagger


_UNIDIC_WAKA_ZIP_URL = "https://clrd.ninjal.ac.jp/unidic_archive/2512/unidic-waka-v202512.zip"


def _ext(name: str) -> str:
    # 拡張子を小文字で返す
    return os.path.splitext(name.lower())[1]


def _as_output_bytes(
    output_format: str,
    texts: List[str],
) -> Tuple[bytes, str]:
    # 指定形式に合わせて出力バイト列とMIMEを返す
    if output_format == "txt":
        return texts_to_txt_bytes(texts), "text/plain"
    if output_format == "csv":
        return texts_to_csv_bytes(texts), "text/csv"
    if output_format == "xml":
        return texts_to_xml_bytes(texts), "application/xml"
    raise ValueError(f"Unsupported output format: {output_format}")


def _local_name(tag: str) -> str:
    # 名前空間付きタグからローカル名だけを取り出す
    return tag.split("}", 1)[1] if "}" in tag else tag


def _load_xml_with_sourceline(data: bytes):
    # 行番号を取るためにiterparseを使ってXMLを読み込む
    import xml.etree.ElementTree as ET

    parser = ET.XMLParser()
    it = ET.iterparse(io.BytesIO(data), events=("start",), parser=parser)
    elements = []
    for _, elem in it:
        elements.append(elem)
    return ET.ElementTree(elements[0]) if elements else None


def _extract_l_and_seg(tree, l_tag: str, seg_tag: str):
    # <l>とその配下の<seg>を抽出する
    root = tree.getroot()
    l_items = []
    for elem in root.iter():
        if _local_name(elem.tag) != l_tag:
            continue
        segs = [s for s in elem.iter() if _local_name(s.tag) == seg_tag]
        l_items.append((elem, segs))
    return l_items


def _index_l_elements(tree, l_tag: str) -> List:
    # <l>要素を順番通りに取得する
    root = tree.getroot()
    return [e for e in root.iter() if _local_name(e.tag) == l_tag]


def _map_original_l(orig_tree, l_tag: str):
    # xml:id / n / 出現順で元の<l>要素を参照できるようにする
    id_map: Dict[str, object] = {}
    n_map: Dict[str, object] = {}
    ordered = _index_l_elements(orig_tree, l_tag)
    for elem in ordered:
        xml_id = elem.attrib.get("{http://www.w3.org/XML/1998/namespace}id", "")
        n_attr = elem.attrib.get("n", "")
        if xml_id:
            id_map[xml_id] = elem
        if n_attr:
            n_map[n_attr] = elem
    return id_map, n_map, ordered


def _seg_text(seg) -> str:
    # seg内のテキストだけ取得（rdg/rtは除外）
    parts: List[str] = []

    def walk(node):
        if _local_name(node.tag) in ("rdg", "rt"):
            return
        if node.text:
            parts.append(node.text)
        for child in list(node):
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(seg)
    return "".join(parts)


def _has_dicrc(path: str) -> bool:
    # dicrcがあるフォルダかどうか
    return bool(path) and os.path.isfile(os.path.join(path, "dicrc"))


def _find_dicrc_dir(root: str) -> str:
    # 配下からdicrcを探してその親フォルダを返す
    for dirpath, _, filenames in os.walk(root):
        if "dicrc" in filenames:
            return dirpath
    return ""


def _ensure_unidic_waka(preferred_dir: str) -> str:
    # dicrcが無い場合はサーバー側でUniDicを自動取得する
    if _has_dicrc(preferred_dir):
        return preferred_dir

    cache_root = os.path.join(os.path.expanduser("~"), ".cache", "waka_kana_conv")
    target_dir = os.path.join(cache_root, "unidic-waka")
    if _has_dicrc(target_dir):
        return target_dir

    os.makedirs(cache_root, exist_ok=True)

    # SSL検証無効化とUser-Agent設定（ブロック回避用）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(_UNIDIC_WAKA_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            zip_data = resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(
            f"辞書データの自動ダウンロードに失敗しました。\n"
            f"サイドバーの「辞書の手動設定」から、手元でダウンロードしたZIPファイルをアップロードしてください。\n"
            f"詳細エラー: {e}"
        )

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        zf.extractall(cache_root)

    found = _find_dicrc_dir(cache_root)
    return found if found else preferred_dir


# 画面設定とタイトル
st.set_page_config(page_title="仮名変換ツール", layout="wide")
st.title("仮名変換ツール")

st.markdown(
    "和歌本文を MeCab + 和歌UniDic で形態素解析し、読みを抽出して仮名変換します。"
)

# 使い方ガイド
with st.expander("使い方ガイド", expanded=False):
    st.markdown(
        "\n".join(
            [
                "1. 入力ファイルがXMLの場合は「XML本文タグ名」に仮名に変換したい本文のタグ名（例: `l` や `seg`）を入れます。",
                "   入力ファイルがCSVの場合は、「CSV本文列名」に仮名に変換したい本文の列名を入れます。",
                "2. 出力形式（txt / csv / xml）を選びます。",
                "3. 画面中央の「入力ファイル」からファイルを選び、「変換する」を押します。",
                "※ 初回は和歌UniDicの自動ダウンロードが走るため、少し時間がかかることがあります。",
            ]
        )
    )

# チェックモードの説明
with st.expander("チェックモードについて", expanded=False):
    st.markdown(
        "\n".join(
            [
                "- MeCabと和歌UniDicによる仮名変換では誤りが生じる可能性があります。",
                "- 和歌各句が `seg` タグ等で区切られているXMLであれば、文字数を参考に誤りの可能性がある和歌を一覧できます。",
                "- ただし字余り・字足らずの和歌も検出されます。",
                "- 誤っていても偶然 5,7,5,7,7 になる場合は検出できません。",
                "- あくまで補助的なツールとしてご利用ください。",
            ]
        )
    )
    st.markdown("チェックモードの使い方")
    st.markdown(
        "\n".join(
            [
                "1. 「和歌XMLチェック」タブを開く",
                "2. 「もとのXMLデータ」と「かな変換後のXMLデータ」を指定",
                "   - 変換タブでXMLを処理済みの場合は、自動的に候補として選べます",
                "3. 行タグ名（例: `l`）と句タグ名（例: `seg`）を指定",
                "4. 「チェックする」を押す",
                "5. 不一致がある場合は、その場で修正して修正済みXMLをダウンロードできます",
            ]
        )
    )

# サイドバー設定
with st.sidebar:
    st.header("設定")
    dic_dir = os.path.join(os.getcwd(), "unidic-waka")
    auto_download = True
    mecabrc_path = os.environ.get("MECABRC", "")
    expand_odoriji = st.checkbox(
        "踊り字（ゝゞヽヾ）を展開する",
        value=True,
        help="踊り字を直前文字で展開します。",
    )
    xml_tag = st.text_input("XML本文タグ名", value="l")
    csv_column = st.text_input("CSV本文列名", value="text")
    output_format = st.selectbox("出力形式", ["txt", "csv", "xml"], index=2)
    output_mode = st.selectbox("出力モード", ["ひらがな", "カタカナ"])
    zip_download = st.checkbox("複数ファイルをZIPで一括ダウンロードする", value=False)
    st.caption("docx入力は txt と docx を両方出力します。")

    with st.expander("辞書の手動設定（自動DL失敗時）"):
        st.markdown(
            "自動ダウンロードが失敗する場合、[公式サイト](https://clrd.ninjal.ac.jp/unidic/download_all.html)から和歌UniDicをダウンロードし、ここにアップロードしてください。"
        )
        manual_zip = st.file_uploader("unidic-waka ZIP", type=["zip"], key="manual_dic")
        if manual_zip:
            cache_root = os.path.join(os.path.expanduser("~"), ".cache", "waka_kana_conv")
            os.makedirs(cache_root, exist_ok=True)
            try:
                with zipfile.ZipFile(manual_zip) as zf:
                    zf.extractall(cache_root)
                st.success("辞書をインストールしました。変換を試してください。")
            except Exception as e:
                st.error(f"ZIPの展開に失敗しました: {e}")

tab_convert, tab_check = st.tabs(["変換", "和歌XMLチェック"])

preview_items = []
if "check_xml_pairs" not in st.session_state:
    st.session_state["check_xml_pairs"] = []

with tab_convert:
    uploaded = st.file_uploader(
        "入力ファイル (.txt / .docx / .csv / .xml)",
        type=["txt", "docx", "csv", "xml"],
        accept_multiple_files=True,
    )

    if uploaded and st.button("変換する"):
        try:
            dic_dir_to_use = _ensure_unidic_waka(dic_dir) if auto_download else dic_dir
        except RuntimeError as e:
            st.error(str(e))
            st.stop()

        if not _has_dicrc(dic_dir_to_use):
            st.error("和歌UniDicのフォルダに dicrc が見つかりません。パスを確認してください。")
            st.stop()
        try:
            # MeCabの初期化
            tagger = create_tagger(dic_dir_to_use, mecabrc_path or None, 20)
        except Exception as exc:
            st.error(f"MeCabの初期化に失敗しました: {exc}")
            st.stop()

        zip_buffer = io.BytesIO()
        zip_file = zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED)

        for file in uploaded:
            # ファイルごとに処理
            name = file.name
            data = file.read()
            ext = _ext(name)

            st.subheader(name)

            if ext == ".txt":
                # txt: 全文を変換
                text = read_text_bytes(data)
                converted = convert_text(
                    text,
                    tagger,
                    expand_odoriji,
                    "katakana" if output_mode == "カタカナ" else "hiragana",
                )
                out_bytes, mime = _as_output_bytes(output_format, [converted])
                out_name = f"{os.path.splitext(name)[0]}.{output_format}"
                if zip_download:
                    zip_file.writestr(out_name, out_bytes)
                else:
                    st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)
                preview_items.append((out_name, text, converted))

            elif ext == ".docx":
                # docx: 段落ごとに変換してtxt/docx両方出力
                txt_bytes, docx_bytes = convert_docx_bytes(
                    data,
                    lambda t: convert_text(
                        t,
                        tagger,
                        expand_odoriji,
                        "katakana" if output_mode == "カタカナ" else "hiragana",
                    ),
                )
                base = os.path.splitext(name)[0]
                if zip_download:
                    zip_file.writestr(f"{base}.txt", txt_bytes)
                    zip_file.writestr(f"{base}.docx", docx_bytes)
                else:
                    st.download_button(
                        "TXTをダウンロード",
                        data=txt_bytes,
                        file_name=f"{base}.txt",
                        mime="text/plain",
                    )
                    st.download_button(
                        "DOCXをダウンロード",
                        data=docx_bytes,
                        file_name=f"{base}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                try:
                    preview_text = txt_bytes.decode("utf-8-sig", errors="replace")
                    preview_items.append((f"{base}.txt", preview_text, preview_text))
                except Exception:
                    pass

            elif ext == ".csv":
                # csv: 指定列のみ変換して構造を保持
                try:
                    df = convert_csv_bytes(
                        data,
                        csv_column,
                        lambda t: convert_text(
                            t,
                            tagger,
                            expand_odoriji,
                            "katakana" if output_mode == "カタカナ" else "hiragana",
                        ),
                    )
                except KeyError as exc:
                    st.error(str(exc))
                    continue
                converted_texts = df[csv_column].astype(str).tolist()
                if output_format == "csv":
                    out_bytes = write_csv(df)
                    out_name = f"{os.path.splitext(name)[0]}.csv"
                    if zip_download:
                        zip_file.writestr(out_name, out_bytes)
                    else:
                        st.download_button(
                            "ダウンロード",
                            data=out_bytes,
                            file_name=out_name,
                            mime="text/csv",
                        )
                    try:
                        import pandas as _pd
                        import io as _io

                        src_df = _pd.read_csv(_io.BytesIO(data), encoding="utf-8", engine="python")
                        original_col = src_df[csv_column].astype(str).tolist()
                        preview_items.append((out_name, "\n".join(original_col), "\n".join(converted_texts)))
                    except Exception:
                        preview_items.append((out_name, "\n".join(converted_texts), "\n".join(converted_texts)))
                else:
                    out_bytes, mime = _as_output_bytes(output_format, converted_texts)
                    out_name = f"{os.path.splitext(name)[0]}.{output_format}"
                    if zip_download:
                        zip_file.writestr(out_name, out_bytes)
                    else:
                        st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)
                    try:
                        import pandas as _pd
                        import io as _io

                        src_df = _pd.read_csv(_io.BytesIO(data), encoding="utf-8", engine="python")
                        original_col = src_df[csv_column].astype(str).tolist()
                        preview_items.append((out_name, "\n".join(original_col), "\n".join(converted_texts)))
                    except Exception:
                        preview_items.append((out_name, "\n".join(converted_texts), "\n".join(converted_texts)))

            elif ext == ".xml":
                # xml: 指定タグ配下のテキストのみ変換
                try:
                    xml_bytes = convert_xml_bytes(
                        data,
                        xml_tag,
                        lambda t: convert_text(
                            t,
                            tagger,
                            expand_odoriji,
                            "katakana" if output_mode == "カタカナ" else "hiragana",
                        ),
                        pre_expand_odoriji=expand_odoriji,
                    )
                except Exception as exc:
                    st.error(f"XMLの読み込みに失敗しました: {exc}")
                    continue

                if output_format == "xml":
                    # xmlとして出力
                    out_name = f"{os.path.splitext(name)[0]}.xml"
                    if zip_download:
                        zip_file.writestr(out_name, xml_bytes)
                    else:
                        st.download_button(
                            "ダウンロード",
                            data=xml_bytes,
                            file_name=out_name,
                            mime="application/xml",
                        )
                    try:
                        import xml.etree.ElementTree as ET

                        orig_root = ET.fromstring(data)
                        orig_snippets = []
                        for elem in orig_root.iter():
                            if _local_name(elem.tag) != xml_tag:
                                continue
                            orig_snippets.append(ET.tostring(elem, encoding="unicode"))

                        conv_root = ET.fromstring(xml_bytes)
                        conv_snippets = []
                        for elem in conv_root.iter():
                            if _local_name(elem.tag) != xml_tag:
                                continue
                            conv_snippets.append(ET.tostring(elem, encoding="unicode"))

                        preview_items.append((out_name, "\n".join(orig_snippets), "\n".join(conv_snippets)))
                    except Exception:
                        pass
                else:
                    # xml以外の場合は本文だけを抽出して出力
                    try:
                        root = xml_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        root = xml_bytes.decode("utf-8", errors="replace")
                    texts = []
                    import xml.etree.ElementTree as ET

                    parsed = ET.fromstring(root)
                    for elem in parsed.iter():
                        if _local_name(elem.tag) != xml_tag:
                            continue
                        texts.append("".join(elem.itertext()))
                    out_bytes, mime = _as_output_bytes(output_format, texts)
                    out_name = f"{os.path.splitext(name)[0]}.{output_format}"
                    if zip_download:
                        zip_file.writestr(out_name, out_bytes)
                    else:
                        st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)
                    try:
                        import xml.etree.ElementTree as ET

                        orig_root = ET.fromstring(data)
                        orig_snippets = []
                        for elem in orig_root.iter():
                            if _local_name(elem.tag) != xml_tag:
                                continue
                            orig_snippets.append(ET.tostring(elem, encoding="unicode"))
                        preview_items.append((out_name, "\n".join(orig_snippets), "\n".join(texts)))
                    except Exception:
                        pass

                # チェックタブ用に変換結果を記憶（複数保持・同名は上書き）
                pair_name = f"{os.path.splitext(name)[0]}.xml"
                replaced = False
                for idx, pair in enumerate(st.session_state["check_xml_pairs"]):
                    if pair["name"] == pair_name:
                        st.session_state["check_xml_pairs"][idx] = {
                            "name": pair_name,
                            "original": data,
                            "converted": xml_bytes,
                        }
                        replaced = True
                        break
                if not replaced:
                    st.session_state["check_xml_pairs"].append(
                        {
                            "name": pair_name,
                            "original": data,
                            "converted": xml_bytes,
                        }
                    )

            else:
                st.warning("未対応の拡張子です。")

        if zip_download:
            zip_file.close()
            zip_buffer.seek(0)
            st.download_button(
                "ZIPをダウンロード",
                data=zip_buffer.getvalue(),
                file_name="converted_outputs.zip",
                mime="application/zip",
            )

    if preview_items:
        st.markdown("### プレビュー（元ファイル / 変換後）")
        names = [name for name, _, _ in preview_items]
        selected = st.selectbox("プレビューするファイル", names)
        for name, original, converted in preview_items:
            if name == selected:
                col_left, col_right = st.columns(2)
                with col_left:
                    st.text_area("元ファイル（指定タグ/列）", value=original, height=300)
                with col_right:
                    st.text_area("変換後（指定タグ/列）", value=converted, height=300)
                break

with tab_check:
    st.subheader("和歌XMLチェック")
    st.markdown("### XMLファイルの指定")
    orig_file = st.file_uploader("もとのXMLデータ", type=["xml"], key="orig_xml")
    conv_file = st.file_uploader("かな変換後のXMLデータ", type=["xml"], key="conv_xml")
    l_tag = st.text_input("行タグ名", value="l")
    seg_tag = st.text_input("句タグ名", value="seg")
    check_odoriji = st.checkbox("踊り字を展開して文字数を数える", value=True)

    stored_pairs = st.session_state.get("check_xml_pairs", [])
    use_session = orig_file is None and conv_file is None and len(stored_pairs) > 0
    selected_pair = None
    if use_session:
        names = [p["name"] for p in stored_pairs]
        selected_name = st.selectbox("変換タブで生成したXMLから選択", names)
        for p in stored_pairs:
            if p["name"] == selected_name:
                selected_pair = p
                break

    if (orig_file and conv_file) or use_session:
        if st.button("チェックする"):
            dic_dir_to_use = _ensure_unidic_waka(dic_dir) if auto_download else dic_dir
            if not _has_dicrc(dic_dir_to_use):
                st.error("和歌UniDicのフォルダに dicrc が見つかりません。パスを確認してください。")
                st.stop()
            try:
                tagger = create_tagger(dic_dir_to_use, mecabrc_path or None, 20)
            except Exception as exc:
                st.error(f"MeCabの初期化に失敗しました: {exc}")
                st.stop()

            if use_session and selected_pair is not None:
                orig_data = selected_pair["original"]
                conv_data = selected_pair["converted"]
            else:
                orig_data = orig_file.read()
                conv_data = conv_file.read()

            orig_tree = _load_xml_with_sourceline(orig_data)
            conv_tree = _load_xml_with_sourceline(conv_data)
            if orig_tree is None or conv_tree is None:
                st.error("XMLの読み込みに失敗しました。")
                st.stop()

            l_items = _extract_l_and_seg(conv_tree, l_tag, seg_tag)
            mismatch_rows = []
            structure_errors = []
            edit_targets = []

            id_map, n_map, ordered = _map_original_l(orig_tree, l_tag)

            for idx, (l_elem, segs) in enumerate(l_items):
                xml_id = l_elem.attrib.get("{http://www.w3.org/XML/1998/namespace}id", "")
                n_attr = l_elem.attrib.get("n", "")
                line_no = getattr(l_elem, "sourceline", None)

                if len(segs) != 5:
                    structure_errors.append(
                        {
                            "xml:id": xml_id,
                            "n": n_attr,
                            "line": line_no,
                            "seg_count": len(segs),
                            "text": "".join(l_elem.itertext()),
                        }
                    )
                    continue

                seg_texts = [_seg_text(s) for s in segs]
                counts = []
                for text in seg_texts:
                    hira = convert_text(text, tagger, check_odoriji, "hiragana")
                    counts.append(len(hira))

                expected = [5, 7, 5, 7, 7]
                if counts != expected:
                    mismatch_rows.append(
                        {
                            "xml:id": xml_id,
                            "n": n_attr,
                            "line": line_no,
                            "counts": counts,
                        }
                    )

                    # 元XML側の<l>を取得
                    orig_l = None
                    if xml_id and xml_id in id_map:
                        orig_l = id_map[xml_id]
                    elif n_attr and n_attr in n_map:
                        orig_l = n_map[n_attr]
                    elif idx < len(ordered):
                        orig_l = ordered[idx]

                    orig_snippet = ""
                    if orig_l is not None:
                        import xml.etree.ElementTree as ET

                        seg_elems = [s for s in orig_l.iter() if _local_name(s.tag) == seg_tag]
                        orig_snippet = "\n".join(
                            [ET.tostring(s, encoding="unicode") for s in seg_elems]
                        )

                    edit_targets.append(
                        (l_elem, segs, seg_texts, orig_snippet, xml_id or n_attr or str(line_no))
                    )

            if mismatch_rows:
                st.markdown("### 不一致の修正")
                with st.form("edit_form"):
                    edits: Dict[str, List[str]] = {}
                    for idx, (l_elem, segs, seg_texts, orig_snippet, label) in enumerate(
                        edit_targets
                    ):
                        row = mismatch_rows[idx]
                        expected = [5, 7, 5, 7, 7]
                        mismatch_idx = [i for i, c in enumerate(row["counts"]) if c != expected[i]]
                        st.markdown(
                            f"**対象: {label}**  "
                            f"(xml:id={row['xml:id']} / n={row['n']} / line={row['line']} "
                            f"/ 文字数={row['counts']})"
                        )
                        if orig_snippet:
                            st.text_area(
                                "もとのXMLデータ（segのみ）",
                                value=orig_snippet,
                                height=120,
                                key=f"orig_{idx}",
                            )
                        cols = st.columns(5)
                        new_vals = []
                        for i in range(5):
                            with cols[i]:
                                if i in mismatch_idx:
                                    st.markdown(
                                        f"<span style='color:#d32f2f;font-weight:600;'>seg{i+1}</span>",
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    st.markdown(f"seg{i+1}")
                                new_vals.append(
                                    st.text_input(
                                        f"seg{i+1} (#{idx})",
                                        value=seg_texts[i],
                                        key=f"seg_{idx}_{i}",
                                        label_visibility="collapsed",
                                    )
                                )
                        edits[str(id(l_elem))] = new_vals
                    submitted = st.form_submit_button("修正XMLを生成")

                if submitted:
                    # 編集内容をXMLに反映（変換後XMLに適用）
                    for l_elem, segs, _, _, _ in edit_targets:
                        key = str(id(l_elem))
                        if key not in edits:
                            continue
                        new_vals = edits[key]
                        for i, seg in enumerate(segs):
                            seg.text = new_vals[i]

                    out_buf = io.BytesIO()
                    conv_tree.write(out_buf, encoding="utf-8", xml_declaration=True)
                    out_buf.seek(0)
                    st.download_button(
                        "修正済みXMLをダウンロード",
                        data=out_buf.getvalue(),
                        file_name="checked_and_fixed.xml",
                        mime="application/xml",
                    )
            else:
                st.markdown("### 不一致の修正")
                st.write("不一致はありません。")

            st.markdown("### 構造エラー一覧（seg数が5以外）")
            if structure_errors:
                for row in structure_errors:
                    st.write(
                        f"xml:id={row['xml:id']} / n={row['n']} / line={row['line']} "
                        f"→ seg数={row['seg_count']}"
                    )
                    st.text_area(
                        "lタグ内テキスト",
                        value=row.get("text", ""),
                        height=120,
                        key=f"struct_text_{row['xml:id']}_{row['n']}_{row['line']}",
                    )
            else:
                st.write("構造エラーはありません。")
    else:
        st.info("もとのXMLデータと、かな変換後のXMLデータを両方指定してください。")
