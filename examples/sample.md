# iroha-reader-cli サンプル

これは iroha-reader-cli の動作確認用のサンプル文書です。
Markdown の見出しやリストは読み上げ用に除去されます。

## 特徴

- テキストを文単位で分割します
- 各行に開始時刻を付けて LRC を作ります
- 音声は一つのファイルに結合されます

```python
# code blocks are skipped by default
print("hello")
```

長い文は指定した最大文字数で折り返されます。たとえばこの文はある程度長いので、途中の読点で分割される可能性があります。
