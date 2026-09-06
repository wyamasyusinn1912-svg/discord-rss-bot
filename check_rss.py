import os
import json
import urllib.request
import xml.etree.ElementTree as ET

RSS_URL = "https://rss.app/r/feed/89eTgfMGhMoy1irn"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
STATE_FILE = "last_seen.txt"


def fetch_rss():
    request = urllib.request.Request(
        RSS_URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def get_items(data):
    root = ET.fromstring(data)
    items = []

    # RSS形式
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

    # Atom形式
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

        items.append({
            "id": item_id,
            "title": title,
            "link": link
        })

    return items


def send_discord(item):
    message = f"🔔 **新着通知**\n\n**{item['title']}**"

    if item["link"]:
        message += f"\n\n🔗 {item['link']}"

    payload = {
        "username": "非公式通知BOT",
        "content": message
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discordへの送信に失敗しました: {response.status}"
            )


def main():
    data = fetch_rss()
    items = get_items(data)

    if not items:
        print("RSSから記事を取得できませんでした。")
        return

    # 最新記事
    latest = items[0]

    old_id = ""

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_id = f.read().strip()

    # 初回は通知せず、最新記事を記録
    if not old_id:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(latest["id"])

        print("初回設定完了。既存記事は通知しません。")
        return

    # 新着記事を探す
    new_items = []

    for item in items:
        if item["id"] == old_id:
            break

        new_items.append(item)

    # 古い順に通知
    for item in reversed(new_items):
        print(f"新着通知: {item['title']}")
        send_discord(item)

    # 最新記事を保存
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(latest["id"])

    print(f"{len(new_items)}件の新着を処理しました。")


if __name__ == "__main__":
    main()
