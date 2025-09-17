# mamegen

軽量なモックデータ用 DSL パーサ（Python 3.11+）。正規表現ゴリ押しを避け、読みやすさ重視で実装。  
機能: `seq / digits / step / enum / fixed / copy / join / range / date(_range) / reference / value_source`（標準ライブラリのみで実行）.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e .
```
### サンプル DSL

`examples/` ディレクトリに複数のサンプル DSL ファイルを用意しています。

```bash
# ログデータサンプルを CSV で生成
python -m mamegen.cli examples/logs.mgen out.csv

# ユーザー情報サンプルを JSON で生成
python -m mamegen.cli examples/user_info_json.mgen out.json

### 最小実行例

```dsl
mamegen {
  CONFIG {
    type CSV
    count 8
    reproducible true
  }

  HEADER { ["log_id","user_id","timestamp","action","detail"] }

  COLUMN_RULES {
    LABEL "log_id" {
      seq 1
    }
    LABEL "user_id" {
      seq 1000
    }
    LABEL "timestamp" {
      datetime
    }
    LABEL "action" {
      enum ["LOGIN","LOGOUT","VIEW","PURCHASE"]
    }
    LABEL "detail" {
      charset alphabet
      length 20
    }
  }
}
```

### 実行方法

#### 開発環境から直接実行
```bash
python -m mamegen.cli examples/sample.mgen out.csv
```

#### インストール後（エントリポイント利用）
`pip install -e .`

```bash
mamegen examples/sample.mgen out.csv
```

- 出力形式は**拡張子優先**（`.json` なら JSON、それ以外は `CONFIG.type` を使用）。
- 文字コードは `CONFIG.output_encoding` → `CONFIG.encoding` → `utf-8` の順に解決。

## DSLの見取り図（超概要）
- `CONFIG` … 出力形式や件数、乱数固定、エンコーディング、ヘッダ/クオート指定など。
- `HEADER` … 列名の配列を定義。
- `REFERENCE` … ラベル/値テーブル（2列）を定義。
- `CLASS` … 出力データ型を定義。
- `COLUMN_RULES` … 列ごとの生成ルール。INDEX/INDICES/LABEL/LABELS セレクタ対応。

詳しくは **SPEC.md** を参照。

## 主なルール例

- 連番（上限省略の open range 可 / digits でゼロ埋め）

seq 1
digits 4

- ランダム文字列（既定 pool は英数）

charset alphabet
length 8

- 日付範囲指定（フォーマット自動/指定可）

date_range "2020-01-01".."2020-12-31" date
datetime

- 逆引き（左の label 自動検出 or 列名明示）

reference "Q1" output label
reference "Q1" output value
value_source "Q1"

## NULL制御
- `allow_null true|false` と `null_probability 0..1` を列ルールに設定。実装は `allowNull/nullProbability` に正規化され、`allow_null=false` のときは必ず非NULL。

## 出力オプション（CSV/JSON）
- CSV: `with_header` / `quote_strings` / `quote_header` / `encoding` を指定可。
- JSON: `write_json(..., encoding=...)` でエンコーディング反映。

## 制限・注意
- `regex` 生成はミニマル（クラス展開など簡易）。
- 同名ヘッダは非推奨。競合は「後勝ち」。
- `REFERENCE` は空不可（ポリシー次第でNULL返しもあり得るが既定はエラー）。

## 開発・テスト
```bash
PYTHONPATH=. python -m pytest -q
```
## フィードバック / アイディア募集

このプロジェクトに関して「こういう機能が欲しい」といった
アイディアやご意見があれば、ぜひ Issue にてお知らせください。

バグ修正や機能追加を必ず行う保証はありませんが、
いただいたフィードバックは今後の参考にさせていただきます。

## ライセンス / 貢献
このプロジェクトは [MIT License](./LICENSE) のもとで公開されています。 

※ 本ソフトウェアは現状のまま提供されます。いかなる保証もなく、  
バグ修正や機能追加などの対応を行う義務は負いません。
