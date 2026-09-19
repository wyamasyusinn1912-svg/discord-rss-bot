import os
import re
import json
import html
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


# ============================================================
# 設定
# ============================================================

USERNAME = "StarWard_JP"

TIMELINE_URL = (
    f"https://syndication.twitter.com/"
    f"srv/timeline-profile/screen-name/{USERNAME}"
)

TWEET_RESULT_URL = "https://cdn.syndication.twimg.com/tweet-result"

LAST_SEEN_FILE = "last_seen.txt"

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


# ============================================================
# HTTP
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def http_get(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


# ============================================================
# Xタイムライン取得
# ============================================================

def fetch_timeline():
    print("Xタイムライン取得を開始します。")
    print(f"対象アカウント: @{USERNAME}")
    print(f"URL: {TIMELINE_URL}")

    try:
        text = http_get(TIMELINE_URL)

        marker_start = '<script id="__NEXT_DATA__" type="application/json">'
        marker_end = "</script>"

        start = text.find(marker_start)

        if start == -1:
            raise RuntimeError(
                "__NEXT_DATA__ が見つかりませんでした。"
                "X側の仕様変更またはアクセス制限の可能性があります。"
            )

        start += len(marker_start)

        end = text.find(marker_end, start)

        if end == -1:
            raise RuntimeError(
                "__NEXT_DATA__ の終了位置が見つかりませんでした。"
            )

        json_text = text[start:end]

        data = json.loads(json_text)

        print("Xタイムライン取得成功。")

        return data

    except urllib.error.HTTPError as e:
        body = ""

        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        print(f"X取得エラー HTTP {e.code}")
        print(body[:1000])

        raise

    except Exception as e:
        print(f"X取得エラー: {e}")
        raise


# ============================================================
# 再帰的にTweetを探す
# ============================================================

def find_tweets(obj, results=None):
    if results is None:
        results = []

    if isinstance(obj, dict):

        # timeline entries の tweet
        if "tweet" in obj and isinstance(obj["tweet"], dict):
            tweet = obj["tweet"]

            if (
                tweet.get("id_str")
                and (
                    tweet.get("full_text")
                    or tweet.get("text")
                )
            ):
                results.append(tweet)

        # 再帰探索
        for value in obj.values():
            find_tweets(value, results)

    elif isinstance(obj, list):

        for value in obj:
            find_tweets(value, results)

    return results


# ============================================================
# Tweetを整理
# ============================================================

def normalize_tweets(data):
    raw_tweets = find_tweets(data)

    unique = {}

    for tweet in raw_tweets:

        tweet_id = str(tweet.get("id_str", "")).strip()

        if not tweet_id:
            continue

        text = tweet.get("full_text") or tweet.get("text") or ""

        user = tweet.get("user") or {}

        screen_name = (
            user.get("screen_name")
            or USERNAME
        )

        name = (
            user.get("name")
            or "星の翼【公式】"
        )

        created_at = tweet.get("created_at", "")

        permalink = tweet.get("permalink")

        if not permalink:
            permalink = (
                f"https://x.com/{screen_name}/status/{tweet_id}"
            )

        unique[tweet_id] = {
            "id": tweet_id,
            "text": text,
            "created_at": created_at,
            "name": name,
            "screen_name": screen_name,
            "permalink": permalink,
        }

    tweets = list(unique.values())

    # 新しい順
    tweets.sort(
        key=lambda x: int(x["id"]),
        reverse=True
    )

    return tweets


# ============================================================
# Tweet詳細取得
# 画像などのメディアを取得する
# ============================================================

def make_tweet_token(tweet_id):
    """
    Xのsyndication tweet-resultで使用されている
    公開token計算方式。
    """

    value = (int(tweet_id) / 1e15) * 3.141592653589793

    token = format(value, "g")

    # JavaScriptの toString(36) 相当をPythonで再現
    integer_part = int(value)

    chars = "0123456789abcdefghijklmnopqrstuvwxyz"

    if integer_part == 0:
        base36 = "0"
    else:
        n = integer_part
        base36 = ""

        while n > 0:
            n, remainder = divmod(n, 36)
            base36 = chars[remainder] + base36

    fractional = value - integer_part

    if fractional:
        frac = ""
        count = 0

        while fractional and count < 12:
            fractional *= 36
            digit = int(fractional)
            fractional -= digit
            frac += chars[digit]
            count += 1

        base36 += frac

    return base36.lstrip("0")


def fetch_tweet_detail(tweet_id):
    try:

        token = make_tweet_token(tweet_id)

        url = (
            f"{TWEET_RESULT_URL}"
            f"?id={tweet_id}"
            f"&token={urllib.parse.quote(token)}"
        )

        data = http_get_json(url)

        return data

    except Exception as e:

        print(
            f"Tweet詳細取得失敗: {tweet_id}: {e}"
        )

        return None


# ============================================================
# メディア抽出
# ============================================================

def extract_media(tweet_detail):

    if not tweet_detail:
        return []

    media_urls = []

    # mediaDetails
    media_details = tweet_detail.get("mediaDetails") or []

    for media in media_details:

        media_type = media.get("type")

        if media_type == "photo":

            url = media.get("media_url_https")

            if url:
                media_urls.append(url)

        elif media_type == "animated_gif":

            url = media.get("media_url_https")

            if url:
                media_urls.append(url)

        elif media_type == "video":

            # Discord webhookでは動画URLそのものより
            # サムネイル画像を優先
            url = media.get("media_url_https")

            if url:
                media_urls.append(url)

    # photos
    photos = tweet_detail.get("photos") or []

    for photo in photos:

        url = photo.get("url")

        if url:
            media_urls.append(url)

    # 重複除去
    result = []

    for url in media_urls:

        if url not in result:
            result.append(url)

    return result[:4]


# ============================================================
# last_seen
# ============================================================

def load_last_seen():

    if not os.path.exists(LAST_SEEN_FILE):
        return ""

    try:

        with open(
            LAST_SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            value = f.read().strip()

            # 旧RSS版のURL/GUIDからTweet IDを抽出
            match = re.search(
                r"(?:status/|tweet/)(\d+)",
                value
            )

            if match:
                return match.group(1)

            # 数字だけならそのまま
            if value.isdigit():
                return value

            return ""

    except Exception:
        return ""


def save_last_seen(tweet_id):

    with open(
        LAST_SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(str(tweet_id))


# ============================================================
# Discord送信
# ============================================================

def send_discord(tweet, media_urls):

    if not DISCORD_WEBHOOK:
        raise RuntimeError(
            "DISCORD_WEBHOOK が設定されていません。"
        )

    text = tweet["text"].strip()

    if len(text) > 1900:
        text = text[:1890] + "..."

    content = (
        "🔔 **星の翼【公式】 新着投稿**\n\n"
        f"{text}\n\n"
        f"🔗 {tweet['permalink']}"
    )

    payload = {
        "username": "非公式通知BOT",
        "content": content,
        "allowed_mentions": {
            "parse": []
        }
    }

    # 画像がある場合はEmbedとして表示
    if media_urls:

        embeds = []

        for index, image_url in enumerate(media_urls):

            embed = {
                "url": tweet["permalink"]
            }

            if index == 0:
                embed["image"] = {
                    "url": image_url
                }

            else:
                embed["thumbnail"] = {
                    "url": image_url
                }

            embeds.append(embed)

        payload["embeds"] = embeds[:10]

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Discord RSS Bot",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            status = response.status

            print(
                f"Discord送信成功: HTTP {status}"
            )

    except urllib.error.HTTPError as e:

        error_body = ""

        try:
            error_body = (
                e.read()
                .decode(
                    "utf-8",
                    errors="replace"
                )
            )
        except Exception:
            pass

        print(
            f"Discord送信エラー: HTTP {e.code}"
        )

        print(error_body)

        raise


# ============================================================
# メイン
# ============================================================

def main():

    print("=" * 40)
    print("X → Discord 通知Bot")
    print("=" * 40)

    if not DISCORD_WEBHOOK:

        print(
            "ERROR: DISCORD_WEBHOOK がありません。"
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # X取得
    # --------------------------------------------------------

    data = fetch_timeline()

    tweets = normalize_tweets(data)

    print(
        f"取得した投稿数: {len(tweets)}"
    )

    if not tweets:

        print(
            "投稿を取得できませんでした。"
        )

        raise RuntimeError(
            "Xから投稿データを取得できませんでした。"
        )

    # --------------------------------------------------------
    # 最新Tweet
    # --------------------------------------------------------

    latest = tweets[0]

    print(
        f"最新投稿ID: {latest['id']}"
    )

    print(
        f"最新投稿: {latest['text'][:100]}"
    )

    last_seen = load_last_seen()

    print(
        f"前回確認ID: {last_seen or '(なし)'}"
    )

    # --------------------------------------------------------
    # 初回起動
    # --------------------------------------------------------

    if not last_seen:

        print(
            "初回起動なので最新投稿を基準値として保存します。"
        )

        save_last_seen(latest["id"])

        print(
            f"last_seen.txt 更新: {latest['id']}"
        )

        print(
            "初回起動完了。Discord通知は行いません。"
        )

        return

    # --------------------------------------------------------
    # 新着判定
    # --------------------------------------------------------

    try:
        last_seen_int = int(last_seen)
    except ValueError:

        print(
            "last_seen.txt の値を解釈できません。"
        )

        save_last_seen(latest["id"])

        return

    new_tweets = []

    for tweet in tweets:

        try:
            tweet_id_int = int(tweet["id"])
        except ValueError:
            continue

        if tweet_id_int > last_seen_int:

            new_tweets.append(tweet)

    # 古い順に送信
    new_tweets.sort(
        key=lambda x: int(x["id"])
    )

    print(
        f"新着投稿数: {len(new_tweets)}"
    )

    # --------------------------------------------------------
    # 新着なし
    # --------------------------------------------------------

    if not new_tweets:

        print(
            "新着投稿はありません。"
        )

        return

    # --------------------------------------------------------
    # Discord通知
    # --------------------------------------------------------

    successfully_sent = []

    for tweet in new_tweets:

        print("-" * 40)

        print(
            f"新着投稿: {tweet['id']}"
        )

        print(
            tweet["text"][:200]
        )

        # Tweet詳細取得
        detail = fetch_tweet_detail(
            tweet["id"]
        )

        media_urls = extract_media(
            detail
        )

        print(
            f"画像/メディア数: {len(media_urls)}"
        )

        try:

            send_discord(
                tweet,
                media_urls
            )

            successfully_sent.append(
                tweet["id"]
            )

        except Exception:

            print(
                "Discord送信に失敗したため、"
                "last_seenを更新しません。"
            )

            raise

    # --------------------------------------------------------
    # 全送信成功後のみlast_seen更新
    # --------------------------------------------------------

    if successfully_sent:

        newest_sent = successfully_sent[-1]

        save_last_seen(
            newest_sent
        )

        print(
            f"last_seen.txt 更新: {newest_sent}"
        )

    print("=" * 40)
    print("処理完了")
    print("=" * 40)


if __name__ == "__main__":
    main()
