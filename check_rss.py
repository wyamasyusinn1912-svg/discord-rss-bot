import os
import json
import urllib.request
import urllib.error

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]


def test_discord():
    payload = {
        "username": "非公式通知BOT",
        "content": "🔧 Discord Webhook 接続テストです。"
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )

    print("Discord Webhookへ接続テストを開始します。")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print("Discord送信成功")
            print("HTTPステータス:", response.status)
            print("レスポンス:", response.read().decode("utf-8", errors="replace"))

    except urllib.error.HTTPError as e:
        print("Discord送信エラー")
        print("HTTPステータス:", e.code)
        print("レスポンスヘッダー:")
        print(e.headers)
        print("Discordからの返答:")
        print(e.read().decode("utf-8", errors="replace"))
        raise

    except urllib.error.URLError as e:
        print("Discordへの接続自体に失敗しました。")
        print("エラー内容:", e)
        raise


if __name__ == "__main__":
    test_discord()
