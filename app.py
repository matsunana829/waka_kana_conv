import os
from typing import List, Tuple

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


# 画面設定とタイトル
st.set_page_config(page_title="仮名変換ツール", layout="wide")
st.title("仮名変換ツール")

st.markdown(
    "和歌本文を MeCab + 和歌UniDic で形態素解析し、読み（カタカナ）を抽出してひらがな化します。"
)

# サイドバー設定
with st.sidebar:
    st.header("設定")
    dic_dir = st.text_input(
        "和歌UniDicのパス",
        value=os.path.join(os.getcwd(), "unidic-waka"),
    )
    mecabrc_path = st.text_input(
        "mecabrcのパス（任意）",
        value=os.environ.get("MECABRC", ""),
    )
    reading_field = st.number_input(
        "読みフィールド番号（UniDic）",
        min_value=0,
        max_value=30,
        value=20,
        step=1,
        help="辞書の読みフィールド位置。例: 20 を推奨。違和感があれば 6/7/9/20 を試してください。",
    )
    expand_odoriji = st.checkbox(
        "踊り字（ゝゞヽヾ）を展開する",
        value=True,
        help="踊り字を直前文字で展開します。",
    )
    output_format = st.selectbox("出力形式", ["txt", "csv", "xml"])
    csv_column = st.text_input("CSV本文列名", value="text")
    xml_tag = st.text_input("XML本文タグ名", value="text")
    st.caption("docx入力は txt と docx を両方出力します。")

# 入力ファイルのアップロード
uploaded = st.file_uploader(
    "入力ファイル (.txt / .docx / .csv / .xml)",
    type=["txt", "docx", "csv", "xml"],
    accept_multiple_files=True,
)

if uploaded and st.button("変換する"):
    try:
        # MeCabの初期化
        tagger = create_tagger(dic_dir, mecabrc_path or None, int(reading_field))
    except Exception as exc:
        st.error(f"MeCabの初期化に失敗しました: {exc}")
        st.stop()

    for file in uploaded:
        # ファイルごとに処理
        name = file.name
        data = file.read()
        ext = _ext(name)

        st.subheader(name)

        if ext == ".txt":
            # txt: 全文を変換
            text = read_text_bytes(data)
            converted = convert_text(text, tagger, expand_odoriji)
            out_bytes, mime = _as_output_bytes(output_format, [converted])
            out_name = f"{os.path.splitext(name)[0]}.{output_format}"
            st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)

        elif ext == ".docx":
            # docx: 段落ごとに変換してtxt/docx両方出力
            txt_bytes, docx_bytes = convert_docx_bytes(
                data, lambda t: convert_text(t, tagger, expand_odoriji)
            )
            base = os.path.splitext(name)[0]
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

        elif ext == ".csv":
            # csv: 指定列のみ変換して構造を保持
            try:
                df = convert_csv_bytes(
                    data, csv_column, lambda t: convert_text(t, tagger, expand_odoriji)
                )
            except KeyError as exc:
                st.error(str(exc))
                continue
            converted_texts = df[csv_column].astype(str).tolist()
            if output_format == "csv":
                out_bytes = write_csv(df)
                out_name = f"{os.path.splitext(name)[0]}.csv"
                st.download_button(
                    "ダウンロード",
                    data=out_bytes,
                    file_name=out_name,
                    mime="text/csv",
                )
            else:
                out_bytes, mime = _as_output_bytes(output_format, converted_texts)
                out_name = f"{os.path.splitext(name)[0]}.{output_format}"
                st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)

        elif ext == ".xml":
            # xml: 指定タグ配下のテキストのみ変換
            try:
                xml_bytes = convert_xml_bytes(
                    data, xml_tag, lambda t: convert_text(t, tagger, expand_odoriji)
                )
            except Exception as exc:
                st.error(f"XMLの読み込みに失敗しました: {exc}")
                continue

            if output_format == "xml":
                # xmlとして出力
                out_name = f"{os.path.splitext(name)[0]}.xml"
                st.download_button(
                    "ダウンロード",
                    data=xml_bytes,
                    file_name=out_name,
                    mime="application/xml",
                )
            else:
                # xml以外の場合は本文だけを抽出して出力
                try:
                    root = xml_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    root = xml_bytes.decode("utf-8", errors="replace")
                texts = []
                import xml.etree.ElementTree as ET

                def _local_name(tag: str) -> str:
                    return tag.split("}", 1)[1] if "}" in tag else tag

                parsed = ET.fromstring(root)
                for elem in parsed.iter():
                    if _local_name(elem.tag) != xml_tag:
                        continue
                    texts.append("".join(elem.itertext()))
                out_bytes, mime = _as_output_bytes(output_format, texts)
                out_name = f"{os.path.splitext(name)[0]}.{output_format}"
                st.download_button("ダウンロード", data=out_bytes, file_name=out_name, mime=mime)

        else:
            st.warning("未対応の拡張子です。")
