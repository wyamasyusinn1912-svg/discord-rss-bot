import os
import json
import urllib.request
import xml.etree.ElementTree as ET

RSS_URL =  "https://rss.app/feeds/tMndJxDlHKO3z40g.xml"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
STATE_FILE = "last_seen.txt"


def fetch_rss():
    request = urllib.request.Request(
        RSS_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

        print("RSS取得成功")
        print("HTTP:", response.status)
        print("Content-Type:", response.headers.get("Content-Type"))
        print("データ先頭:", data[:500])

        return data


def get_items(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        print("RSSのXML解析に失敗しました。")
        print("受信したデータ:")
        print(data[:2000].decode("utf-8", errors="replace"))
        raise e

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

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print("Discord送信:", response.status)


def main():
    data = fetch_rss()
    items = get_items(data)

    print("取得した記事数:", len(items))

    if not items:
        print("RSSに記事がありません。")
        return

    latest = items[0]

    old_id = ""

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_id = f.read().strip()

    # 初回
    if not old_id:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(latest["id"])

        print("初回設定完了。既存記事は通知しません。")
        return

    new_items = []

    for item in items:
        if item["id"] == old_id:
            break

        new_items.append(item)

    for item in reversed(new_items):
        print("新着通知:", item["title"])
        send_discord(item)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(latest["id"])

    print(f"{len(new_items)}件の新着を処理しました。")


if __name__ == "__main__":
    main()
