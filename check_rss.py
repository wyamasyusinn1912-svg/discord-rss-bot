import os
import json
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

RSS_URL = "https://rss.app/feeds/tMndJxDlHKO3z40g.xml"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
STATE_FILE = "last_seen.txt"

SEND_INTERVAL = 2


def fetch_rss():
    request = urllib.request.Request(
        RSS_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
    )

    print("RSS取得を開始します。")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()

            print("RSS取得成功")
            print("HTTP:", response.status)
            print("Content-Type:", response.headers.get("Content-Type"))
            print("取得データサイズ:", len(data), "bytes")

            return data

    except urllib.error.HTTPError as e:
        print("RSS取得エラー")
        print("HTTPステータス:", e.code)
        print("レスポンス:")
        print(e.read().decode("utf-8", errors="replace"))
        raise

    except urllib.error.URLError as e:
        print("RSSへの接続自体に失敗しました。")
        print("エラー内容:", e)
        raise


def get_items(data):
    print("RSSのXML解析を開始します。")

    try:
        root = ET.fromstring(data)

    except ET.ParseError as e:
        print("RSSのXML解析に失敗しました。")
        print("受信したデータ:")
        print(data[:2000].decode("utf-8", errors="replace"))
        raise

    items = []

    for item in root.findall(".//item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        guid = item.findtext("guid", default="").strip()

        item_id = guid or link or title

        if item_id:
            items.append({
                "id": item_id,
                "title": title,
                "link": link
            })

    atom = "{http://www.w3.org/2005/Atom}"

    for entry in root.findall(f".//{atom}entry"):
        title_element = entry.find(f"{atom}title")
        id_element = entry.find(f"{atom}id")
        link_element = entry.find(f"{atom}link")

        title = (
            title_element.text.strip()
            if title_element is not None and title_element.text
            else ""
        )

        item_id = (
            id_element.text.strip()
            if id_element is not None and id_element.text
            else title
        )

        link = ""

        if link_element is not None:
            link = link_element.attrib.get("href", "")

        if item_id:
            items.append({
                "id": item_id,
                "title": title,
                "link": link
            })

    print("RSS解析成功")
    print("取得した記事数:", len(items))

    return items


def load_last_seen():
    if not os.path.exists(STATE_FILE):
        print("last_seen.txt が存在しません。")
        return ""

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        old_id = f.read().strip()

    print("last_seen.txt のID:", old_id)

    return old_id


def save_last_seen(item_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(item_id)

    print("last_seen.txt を更新しました。")
    print("保存したID:", item_id)


def send_discord(item):
    message = f"🔔 **新着通知**\n\n**{item['title']}**"

    if item["link"]:
        message += f"\n\n🔗 {item['link']}"

    payload = {
        "username": "非公式通知BOT",
        "content": message
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

    print("")
    print("Discordへ送信:")
    print(item["title"])

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print("Discord送信成功")
            print("HTTPステータス:", response.status)
            return True

    except urllib.error.HTTPError as e:
        print("")
        print("Discord送信エラー")
        print("HTTPステータス:", e.code)
        print("Discordからの返答:")
        print(e.read().decode("utf-8", errors="replace"))
        return False

    except urllib.error.URLError as e:
        print("")
        print("Discordへの接続自体に失敗しました。")
        print("エラー内容:", e)
        return False


def find_new_items(items, old_id):
    if not old_id:
        return None

    new_items = []

    for item in items:
        if item["id"] == old_id:
            return new_items

        new_items.append(item)

    print("")
    print("警告:")
    print("last_seen.txt に記録されたIDが現在のRSS内に存在しません。")
    print("安全のため、今回は通知しません。")
    print("last_seen.txt も更新しません。")

    return None


def main():
    print("========================================")
    print("Discord RSS Bot")
    print("========================================")

    data = fetch_rss()

    items = get_items(data)

    if not items:
        print("RSSに記事がありません。")
        return

    latest = items[0]

    print("")
    print("最新記事:")
    print("タイトル:", latest["title"])
    print("ID:", latest["id"])

    old_id = load_last_seen()

    if not old_id:
        save_last_seen(latest["id"])

        print("")
        print("初回設定完了。")
        print("既存記事はDiscordへ通知しません。")
        return

    new_items = find_new_items(items, old_id)

    if new_items is None:
        return

    if not new_items:
        print("")
        print("新着記事はありません。")
        return

    print("")
    print("新着記事:", len(new_items), "件")

    for index, item in enumerate(reversed(new_items), start=1):
        print("")
        print(f"[{index}/{len(new_items)}]")
        print(item["title"])

    success_count = 0

    for index, item in enumerate(
        reversed(new_items),
        start=1
    ):
        print("")
        print("----------------------------------------")
        print(f"Discord送信 {index}/{len(new_items)}")
        print("----------------------------------------")

        success = send_discord(item)

        if not success:
            print("")
            print("Discord送信に失敗しました。")
            print("last_seen.txt は更新しません。")
            return

        success_count += 1

        if index < len(new_items):
            print(f"{SEND_INTERVAL}秒待機します。")
            time.sleep(SEND_INTERVAL)

    save_last_seen(latest["id"])

    print("")
    print("========================================")
    print("処理完了")
    print("========================================")
    print("新着記事:", len(new_items), "件")
    print("Discord送信成功:", success_count, "件")
    print("last_seen.txt: 更新済み")
    print("========================================")


if __name__ == "__main__":
    main()
