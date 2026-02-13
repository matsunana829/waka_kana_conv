# 仮名変換ツール

和歌本文を MeCab + 和歌UniDic で形態素解析し、読みを抽出して仮名変換する Streamlit アプリです。

## ご使用になる前に（MeCab本体のインストール）
`mecab-python3` は **Pythonのバインディング** であり、**MeCab本体** は別途インストールが必要です。

### Windows
1. Windows用インストーラを入手してインストール  
2. `mecabrc` の場所を確認（例: `C:\Program Files\MeCab\etc\mecabrc`）  
3. 環境変数 `MECABRC` を設定  

参考URL（公式ページおよび入手先）  
```
https://taku910.github.io/mecab/
```
```
https://rmecab.jp/new/install-rmecab/
```
64bit版の入手先（公式のexeが入手できない場合の代替）  
```
https://github.com/ikegami-yukino/mecab/releases/tag/v0.996
```

### macOS
Homebrewでインストールするのが簡単です。  
```
brew install mecab
brew install mecab-ipadic
```
参考URL  
```
https://luteorg.github.io/lute-manual/install/mecab.html
```

## 和歌UniDicのダウンロードと配置
1. ブラウザで以下を開き、和歌UniDic（unidic-waka）のZIPをダウンロード  
```
https://clrd.ninjal.ac.jp/unidic/download_all.html
```
2. ダウンロードしたZIPを右クリックして「すべて展開」を選択  
3. 展開されたフォルダ（例: `unidic-waka`）を分かりやすい場所に置く  
   - 例: `C:\Users\Nana\Desktop\unidic-waka`  
4. そのフォルダの中に `dicrc` があることを確認  

## 使い方
1. 依存関係をインストール  
   - `pip install -r requirements.txt`
2. MeCab本体をインストールし、`mecabrc` を設定  
   - 例: `C:\Program Files\MeCab\etc\mecabrc`
3. 和歌UniDicを配置  
   - 例: `...\unidic-waka\`（`dicrc` が存在すること）
4. アプリを起動  
   - `streamlit run app.py`

## アプリ使い方ガイド
1. 画面左の「設定」にある「和歌UniDicのパス」にフォルダの場所を入れます  
   - 例: `C:\Users\Nana\Desktop\unidic-waka`  
   - フォルダの場所はエクスプローラーのアドレスバーをコピーすると確実です。  
2. 「mecabrcのパス」は、空欄のままで動けばそのままでOKです  
   - エラーが出た場合のみ `C:\Program Files\MeCab\etc\mecabrc` を入れてください。  
   - それでもエラーが出る場合は、コンピューター内のmecabrcがある位置を確認して、和歌UniDicと同様にそのパスを入れてください。  
3. 入力ファイルがXMLの場合は「XML本文タグ名」に仮名に変換したい本文のタグ名（例: `l` や `seg`）を入れます  
   入力ファイルがCSVの場合は、「CSV本文列名」に仮名に変換したい本文の列名を入れます  
4. 出力形式（txt / csv / xml）を選びます  
5. 画面中央の「入力ファイル」からファイルを選び、「変換する」を押します  

## チェックモードについて
MeCabと和歌UniDicによる仮名変換では誤りが生じる可能性があります。  
その確認をしやすくするため、**和歌各句が `seg` タグで区切られているXML** に対して、  
ひらがな変換後の文字数が **5-7-5-7-7** になっているかを確認するチェック機能を用意しています。  

ただし以下の制約があります。  
- **字余り・字足らずの和歌**も検出対象になるため、必ずしも誤りとは限りません。  
- **誤りがあっても偶然 5-7-5-7-7 になる場合は検出できません。**  
  
このため、**チェックモードは補助的なツール**としてご利用ください。  

### チェックモードの使い方
1. 「和歌XMLチェック」タブを開く  
2. 「もとのXMLデータ」と「かな変換後のXMLデータ」を指定  
   - 変換タブでXMLを処理済みの場合は、自動的に候補として選べます  
3. 行タグ名（例: `l`）と句タグ名（例: `seg`）を指定  
4. 「チェックする」を押す  
5. 不一致がある場合は、その場で修正して修正済みXMLをダウンロードできます  

## 入力形式
- `.txt` / `.docx` / `.csv` / `.xml`

## 出力形式
- `.txt` / `.csv` / `.xml`
- `.docx` 入力時は **txt と docx を両方出力**

## メモ
- CSV/XML は本文フィールドのみ変換し、構造を保持します。
- 未知語は原文を保持します。