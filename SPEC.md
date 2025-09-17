# Mamegen DSL Specification

- **Runtime**
  - Python 3.11+
  - Standard library only (no extra runtime deps)

- **Development**
  - pytest (testing)
  - black (formatting)

## 全体構成

DSL ファイルは以下の 5 セクションで構成される。

- CONFIG
- HEADER
- REFERENCE
- CLASS
- COLUMN_RULES


順序は固定されていないが、1 ファイル中で各セクションは複数回書ける
（例：REFERENCE を複数キーで繰り返し定義可能）。

### CONFIG

-   出力の基本設定を記述する。
-   **1 行につき 1 設定のみ記述可能**。
-   値の区切りは必ず **スペース** を使う。
-   `:` や `=` は使用不可。
-   単一設定をインラインで書く場合は `CONFIG { key value }`
    の形式のみ許可。
-   複数設定を同一行に並べることは禁止。

例:

```dsl
CONFIG {
    type CSV
    count 5
    reproducible true
    output_encoding "utf-8"
}
```

または

```dsl
CONFIG { type CSV }
```

-   `type`: `CSV` | `JSON`
-   `count`: 生成件数
-   `reproducible`: `true/false`（固定seed）
-   `output_encoding`: `"utf-8"` など

------------------------------------------------------------------------

### HEADER

-   出力ヘッダ行の定義。

例:

```dsl
HEADER { ["id","name","birth","email"] }
```

------------------------------------------------------------------------

### REFERENCE
  - ラベルと値の 2 列で定義する。1 行 = 1 ペア。
  - 1 行 = 1 ペア。ラベルはクォート必須（"..." または '...'）。
  - 値は 整数 / 浮動小数 / クォート文字列 のいずれか。余分なトークンがある行はエラー。
  - 値の区切りは スペース。: や = は使用不可。
  - 次の インライン形式も許可：
```dsl
REFERENCE "Q1" { "A" 1
                 "B" 2
                 "C" 3 }
```

空の REFERENCE はエラー（実装では allow_null に従って空返しにしても良いが既定はエラー）。
※ DSL 全体の原則（1 行 1 ルール / 記号禁止）に従う。

------------------------------------------------------------------------

### CLASS

-   再利用可能なルールを定義。

例:

```dsl
CLASS {
  "person" {
    string 8
    allow_null false
  }
}
```

------------------------------------------------------------------------

## COLUMN_RULES

各列に適用する生成ルールを定義する。対象列は以下の方法で指定できる。

### 1. セレクタ

- **1 行 1 ルール**。同じ行に複数設定を並べない（例: `seq 1.. digits 4` は不可）。
- **パラメータ必須ルールの省略は禁止**。`seq 1..` のような上限省略は不可。必ず `seq 1..1000` のように上下限を明示する。
- **記号禁止**: ルール行では `:` と `=` を使用しない（スペース区切りのみ）。
- 文字列リテラルは `"..."` または `'...'`。未クォートの英数字識別子（`[A-Za-z_]\w*`）は **列参照** とみなす。

#### range
- 数値の範囲を指定するルール。指定された値に応じて、内部的に int または float として扱われる。
- type=range という型は存在せず、整数範囲なら int、小数範囲なら float に自動決定される。

#### 1. 単一列指定

- **INDEX**
  ```dsl
  INDEX n { ... }
  ```
  - ヘッダーの **n 列目 (1 始まり)** にルールを適用する。

- **LABEL**
  ```dsl
  LABEL "colname" { ... }
  ```
  - ヘッダー名が `"colname"` の列にルールを適用する。

#### 2. 複数列指定

- **INDICES**
  ```dsl
  INDICES a..b { ... }        # 範囲指定 (a〜b列を対象)
  INDICES [i1,i2,...] { ... } # 配列指定
  ```
  - ヘッダーの **1 始まりインデックス**で複数列を対象とする。

- **LABELS**
  ```dsl
  LABELS ["col1","col2",...] { ... }  # 配列列挙
  LABELS "col1".."col5" { ... }       # 範囲指定 (HEADER 内の並び順で col1〜col5 を包含)
  ```
  - ヘッダー名を使って複数列を対象とする。
  - 範囲指定では HEADER の並び順に基づき、開始ラベルから終了ラベルまでを対象にする。
  - 開始ラベルまたは終了ラベルが存在しない場合、あるいは終了ラベルが開始より前に出現する場合はエラー。

### 3.COLUMN_RULES からの REFERENCE 参照
#### 評価順序と競合
  - 各レコードの評価は **HEADER の並び順（左→右）**で行う。 
  - 競合時は 後勝ち（下に書かれたルールが優先）。 

#### キーワード

  - reference "<KEY>"
  この列が参照する REFERENCE を指定。
  - output label|value
  参照結果として ラベルか値のどちらを出力するかを指定（現行は 2 択のみ）。
  - value_source / value_source "<colname>"
  逆引きモードを有効化。
  - 引数なし：同一 KEY で 自列より左にある output label 列の直近の値をキーとして逆引き。見つからなければ空（allow_null/null_probabilityに従う）。
  - 引数あり：同一レコード内の <colname> の値をキーとして逆引き。列が無い／空／未ヒット時は空（同上）。
  - 逆引き時は ロックを使わない（逐次評価で確定）。

#### 暗黙ロック（通常参照）
  - value_source を使わない場合、同一レコード内でその KEY を最初に参照した時点で 1 行を抽選しロック。
  - 以降、同じ KEY の参照は 同じ行を返す（同期）。

#### 返り値が空になる条件（NULL 振る舞い）

  - value_source（あり/なしとも）でキー列が見つからない／値が空／逆引き未ヒット
  → 空を返す（allow_null/null_probabilityに従う）。
  - allow_null false の場合は例外とする実装でもよい（実装ポリシーに従う）。

#### 例1：通常の同期参照（暗黙ロック）
```dsl
COLUMN_RULES {
  LABEL "ans_label" {
    reference "Q1"
    output label    # ← 初回参照で Q1 の行がロックされる
  }
  LABEL "ans_value" {
    reference "Q1"
    output value    # ← 同じ行の value を返す（同期）
  }
}
```

#### 例2：逆引き（左のラベル列を自動検出）
```dsl
COLUMN_RULES {
  LABEL "ans_label" {
    reference "Q1"
    output label
  }
  LABEL "ans_value" {
    reference "Q1"
    value_source     # ← 左にある同 KEY の label 列を自動で使う
    output value
  }
}
```

#### 例3：逆引き（参照元列を明示）
```dsl
COLUMN_RULES {
  LABEL "ans_label" {
    reference "Q1"
    output label
  }
  LABEL "ans_value" {
    reference "Q1"
    value_source "ans_label"  # ← 参照元列を明示
    output value
  }
}
```

### 4. 共通仕様

- `{ ... }` 内には通常のルール（`seq`, `charset`, `date_range`, `allow_null`, `null_probability` など）を書く。
- **ルールは 1 行に 1 つだけ記述可能。スペースで複数ルールを並べることは禁止。**
- 適用対象は **HEADER の並び順**に従う。
- 複数セレクタや個別指定が競合した場合は **後勝ち**（下に書いたものが優先）。
- 未知の列名や不正な範囲はエラー (`DSLUnknownColumnError` / `DSLInvalidRuleError`)。
- 同名列は非推奨。出現した場合は最初の列を採用するか、エラーとする実装依存。

---

### 使用例

```dsl
COLUMN_RULES {
  INDEX 1 {
    seq 1..
    digits 4
  }

  INDICES [2,3,4] {
    charset alphabet
    length 8
  }

  INDICES 2..3 {
    charset alphabet
    length 8
  }

  LABELS ["name","email"] {
    allow_null true
    null_probability 0.1
  }

  LABELS "code1".."code5" {
    digits 3
  }
}
```
