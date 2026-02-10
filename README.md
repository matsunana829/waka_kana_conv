# 仮名変換ツール

和歌本文を MeCab + 和歌UniDic で形態素解析し、読み（カタカナ）を抽出してひらがな化する Streamlit アプリです。

## 使い方
1. 依存関係をインストール
   - `pip install -r requirements.txt`
2. MeCab と和歌UniDic をインストール
3. アプリを起動
   - `streamlit run app.py`

## 入力形式
- `.txt` / `.docx` / `.csv` / `.xml`

## 出力形式
- `.txt` / `.csv` / `.xml`
- `.docx` 入力時は **txt と docx を両方出力**

## メモ
- CSV/XML は本文フィールドのみ変換し、構造を保持します。
- 未知語は原文を保持します。
