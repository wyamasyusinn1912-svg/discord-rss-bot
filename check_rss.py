import os
import re
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ============================================================
# 設定
# ============================================================

USERNAME = "StarWard_JP"

TIMELINE_URL = (
    "https://syndication.twitter.com/"
    f"srv/timeline-profile/screen-name/{USERNAME}"
)

TWEET_RESULT_URL = "https://cdn.syndication.twimg.com/tweet-result"

LAST_SEEN_FILE = "last_seen.txt"

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


# ============================================================
# HTTP取得
# ============================================================

def http_get(url, timeout=30, retries=3):
    """
    URLからデータを取得する。
    429 / 5xx の場合は少し待ってリトライする。
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }

    last_error = None

    for attempt in range(1, retries + 1):

        try:
            request = urllib.request.Request(
                url,
                headers=headers,
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:

                status = response.status
                data = response.read()

                if status != 200:
                    raise RuntimeError(
                        f"HTTPステータス: {status}"
                    )

                return data

        except urllib.error.HTTPError as e:

            last_error = e

            print(
                f"HTTPエラー: {e.code} "
                f"(試行 {attempt}/{retries})"
            )

            # レート制限や一時的なサーバーエラーだけリトライ
            if e.code in (429, 500, 502, 503, 504):

                if attempt < retries:
                    wait_time = attempt * 5

                    print(
                        f"{wait_time}秒待って再試行します。"
                    )

                    time.sleep(wait_time)
                    continue

            raise

        except Exception as e:

            last_error = e

            print(
                f"通信エラー: {e} "
                f"(試行 {attempt}/{retries})"
            )

            if attempt < retries:
                wait_time = attempt * 3

                print(
                    f"{wait_time}秒待って再試行します。"
                )

                time.sleep(wait_time)

    raise last_error


# ============================================================
# Xプロフィールタイムライン取得
# ============================================================

def fetch_timeline():
    """
    Xの公開Syndicationタイムラインを取得する。
    """

    print("Xタイムライン取得を開始します。")
    print(f"対象アカウント: @{USERNAME}")
    print(f"URL: {TIMELINE_URL}")

    data = http_get(TIMELINE_URL)

    html_text = data.decode(
        "utf-8",
        errors="replace",
    )

    # __NEXT_DATA__ を探す
    pattern = (
        r'<script[^>]*id="__NEXT_DATA__"'
        r'[^>]*>(.*?)</script>'
    )

    match = re.search(
        pattern,
        html_text,
        re.DOTALL,
    )

    if not match:
        raise RuntimeError(
            "__NEXT_DATA__ が見つかりませんでした。"
        )

    json_text = match.group(1)

    try:
        next_data = json.loads(json_text)

    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"__NEXT_DATA__ のJSON解析に失敗しました: {e}"
        )

    print("Xタイムラインの取得に成功しました。")

    return next_data


# ============================================================
# timeline.entries を探す
# ============================================================

def find_entries(obj):
    """
    JSONの中から timeline.entries を探す。
    """

    if isinstance(obj, dict):

        timeline = obj.get("timeline")

        if isinstance(timeline, dict):

            entries = timeline.get("entries")

            if isinstance(entries, list):
                return entries

        for value in obj.values():

            result = find_entries(value)

            if result is not None:
                return result

    elif isinstance(obj, list):

        for item in obj:

            result = find_entries(item)

            if result is not None:
                return result

    return None


# ============================================================
# 投稿データ抽出
# ============================================================

def extract_tweet_from_entry(entry):
    """
    timeline entry からメインの投稿データを取得する。
    """

    if not isinstance(entry, dict):
        return None

    content = entry.get("content")

    if not isinstance(content, dict):
        return None

    # --------------------------------------------------------
    # 現在よく見られる形式
    # content
    #   -> itemContent
    #       -> tweet_results
    #           -> result
    # --------------------------------------------------------

    item_content = content.get("itemContent")

    if isinstance(item_content, dict):

        tweet_results = item_content.get(
            "tweet_results"
        )

        if isinstance(tweet_results, dict):

            result = tweet_results.get("result")

            if isinstance(result, dict):

                return result

        # 古い形式
        tweet = item_content.get("tweet")

        if isinstance(tweet, dict):
            return tweet

    # --------------------------------------------------------
    # 別形式への対応
    # --------------------------------------------------------

    tweet = content.get("tweet")

    if isinstance(tweet, dict):
        return tweet

    return None


# ============================================================
# 投稿一覧を取得
# ============================================================

def find_tweets(next_data):
    """
    timeline.entries から投稿を抽出する。
    """

    entries = find_entries(next_data)

    if not entries:
        print("timeline.entries が見つかりませんでした。")
        return []

    print(f"timeline.entries: {len(entries)}件")

    tweets = []

    for entry in entries:

        tweet = extract_tweet_from_entry(entry)

        if not isinstance(tweet, dict):
            continue

        legacy = tweet.get("legacy")

        # 新しい形式では legacy の中に本文などが入る
        if isinstance(legacy, dict):

            tweet_id = (
                legacy.get("id_str")
                or tweet.get("rest_id")
                or tweet.get("id_str")
            )

            text = (
                legacy.get("full_text")
                or legacy.get("text")
                or tweet.get("text")
                or ""
            )

            user = legacy.get("user")

            if not isinstance(user, dict):
                user = {}

            # author情報が別場所にある場合
            if not user:

                core = tweet.get("core")

                if isinstance(core, dict):

                    user_results = core.get(
                        "user_results"
                    )

                    if isinstance(
                        user_results,
                        dict,
                    ):

                        user_result = user_results.get(
                            "result"
                        )

                        if isinstance(
                            user_result,
                            dict,
                        ):

                            user = (
                                user_result.get("legacy")
                                or {}
                            )

            screen_name = (
                user.get("screen_name")
                or USERNAME
            )

            name = (
                user.get("name")
                or "星の翼【公式】"
            )

            created_at = (
                legacy.get("created_at")
                or ""
            )

            media = (
                legacy.get("extended_entities", {})
                if isinstance(
                    legacy.get("extended_entities"),
                    dict,
                )
                else {}
            )

            if not tweet_id or not text:
                continue

        else:

            # 古い形式
            tweet_id = (
                tweet.get("id_str")
                or tweet.get("id")
                or tweet.get("rest_id")
            )

            text = (
                tweet.get("full_text")
                or tweet.get("text")
                or ""
            )

            user = tweet.get("user")

            if not isinstance(user, dict):
                user = {}

            screen_name = (
                user.get("screen_name")
                or USERNAME
            )

            name = (
                user.get("name")
                or "星の翼【公式】"
            )

            created_at = (
                tweet.get("created_at")
                or ""
            )

            media = (
                tweet.get("extended_entities", {})
                if isinstance(
                    tweet.get("extended_entities"),
                    dict,
                )
                else {}
            )

            if not tweet_id or not text:
                continue

        # 数字IDであることを確認
        if not str(tweet_id).isdigit():
            continue

        permalink = (
            f"https://x.com/{screen_name}/status/{tweet_id}"
        )

        tweets.append(
            {
                "id": str(tweet_id),
                "text": text,
                "screen_name": screen_name,
                "name": name,
                "created_at": created_at,
                "permalink": permalink,
                "raw_media": media,
            }
        )

    # ID重複を除去
    unique = {}

    for tweet in tweets:
        unique[tweet["id"]] = tweet

    tweets = list(unique.values())

    # 新しい順
    tweets.sort(
        key=lambda x: int(x["id"]),
        reverse=True,
    )

    print(
        f"取得できた投稿数: {len(tweets)}件"
    )

    return tweets


# ============================================================
# Tweet Result API
# ============================================================

def fetch_tweet_detail(tweet_id):
    """
    投稿IDから詳細情報を取得する。
    画像などの補完用。
    """

    url = (
        f"{TWEET_RESULT_URL}"
        f"?id={tweet_id}"
        f"&token=0"
    )

    try:

        data = http_get(
            url,
            timeout=20,
            retries=2,
        )

        result = json.loads(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

        return result

    except Exception as e:

        print(
            f"投稿詳細取得失敗: "
            f"{tweet_id} / {e}"
        )

        # 詳細取得失敗しても本文通知は続行
        return None


# ============================================================
# メディアURL抽出
# ============================================================

def extract_media_from_raw(raw_media):
    """
    timelineのraw_mediaから画像URLを取得する。
    """

    urls = []

    if not isinstance(raw_media, dict):
        return urls

    media_list = raw_media.get("media")

    if not isinstance(media_list, list):
        return urls

    for media in media_list:

        if not isinstance(media, dict):
            continue

        media_url = (
            media.get("media_url_https")
            or media.get("media_url")
        )

        if media_url:
            urls.append(media_url)

    return urls


def extract_media_from_detail(detail):
    """
    tweet-resultの結果から画像URLを取得する。
    """

    urls = []

    if not isinstance(detail, dict):
        return urls

    # --------------------------------------------------------
    # photos
    # --------------------------------------------------------

    photos = detail.get("photos")

    if isinstance(photos, list):

        for photo in photos:

            if not isinstance(photo, dict):
                continue

            url = photo.get("url")

            if url:
                urls.append(url)

    # --------------------------------------------------------
    # mediaDetails
    # --------------------------------------------------------

    media_details = detail.get(
        "mediaDetails"
    )

    if isinstance(media_details, list):

        for media in media_details:

            if not isinstance(media, dict):
                continue

            media_url = (
                media.get("media_url_https")
                or media.get("media_url")
            )

            if media_url:
                urls.append(media_url)

    # 重複削除
    result = []

    for url in urls:

        if url not in result:
            result.append(url)

    return result


def get_media_urls(tweet):
    """
    画像URLを取得する。
    まずタイムラインデータ、
    取れなければtweet-resultを使用。
    """

    # ① タイムラインから取得
    urls = extract_media_from_raw(
        tweet.get("raw_media")
    )

    if urls:
        return urls[:4]

    # ② tweet-resultから取得
    detail = fetch_tweet_detail(
        tweet["id"]
    )

    if detail:

        urls = extract_media_from_detail(
            detail
        )

        if urls:
            return urls[:4]

    return []


# ============================================================
# last_seen.txt
# ============================================================

def load_last_seen():
    """
    last_seen.txtから最後に通知した投稿IDを取得。
    """

    if not os.path.exists(LAST_SEEN_FILE):
        print(
            "last_seen.txt が存在しません。"
        )
        return ""

    try:

        with open(
            LAST_SEEN_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            value = f.read().strip()

    except Exception as e:

        print(
            f"last_seen.txt 読み込み失敗: {e}"
        )

        return ""

    if not value:
        return ""

    # 数字だけの場合
    if value.isdigit():
        return value

    # X URLの場合
    match = re.search(
        r"/status/(\d+)",
        value,
    )

    if match:
        return match.group(1)

    # 古いRSSのGUIDなど
    print(
        "last_seen.txt に有効な投稿IDがありません。"
    )

    return ""


def save_last_seen(tweet_id):
    """
    最後に処理した投稿IDを保存。
    """

    with open(
        LAST_SEEN_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(str(tweet_id))

    print(
        f"last_seen.txt を更新しました: {tweet_id}"
    )


# ============================================================
# Discord通知
# ============================================================

def send_discord(tweet):
    """
    Discord Webhookへ投稿を送信。
    """

    if not DISCORD_WEBHOOK:
        raise RuntimeError(
            "DISCORD_WEBHOOK が設定されていません。"
        )

    text = tweet["text"]

    permalink = tweet["permalink"]

    print(
        f"Discord通知送信: {tweet['id']}"
    )

    media_urls = get_media_urls(
        tweet
    )

    content = (
        "🔔 **星の翼【公式】 新着投稿**\n\n"
        f"{text}\n\n"
        f"🔗 {permalink}"
    )

    payload = {
        "username": "非公式通知BOT",
        "content": content,
        "allowed_mentions": {
            "parse": []
        },
    }

    # 画像がある場合
    if media_urls:

        embeds = []

        for index, media_url in enumerate(
            media_urls[:4]
        ):

            if index == 0:

                embeds.append(
                    {
                        "image": {
                            "url": media_url
                        }
                    }
                )

            else:

                embeds.append(
                    {
                        "thumbnail": {
                            "url": media_url
                        }
                    }
                )

        payload["embeds"] = embeds

    data = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordRSSBot/1.0",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            status = response.status

            if status not in (200, 204):

                raise RuntimeError(
                    f"Discord HTTPステータス: {status}"
                )

    except urllib.error.HTTPError as e:

        body = e.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Discord通知エラー: "
            f"HTTP {e.code} / {body}"
        )

    print(
        "Discord通知成功"
    )


# ============================================================
# メイン処理
# ============================================================

def main():

    print("=" * 40)
    print("X → Discord 通知BOT")
    print("=" * 40)

    if not DISCORD_WEBHOOK:

        print(
            "ERROR: DISCORD_WEBHOOK がありません。"
        )

        return 1

    # --------------------------------------------------------
    # X取得
    # --------------------------------------------------------

    try:

        next_data = fetch_timeline()

    except Exception as e:

        print(
            "Xタイムライン取得エラー"
        )

        print(
            f"詳細: {e}"
        )

        return 1

    # --------------------------------------------------------
    # 投稿抽出
    # --------------------------------------------------------

    tweets = find_tweets(
        next_data
    )

    if not tweets:

        print(
            "投稿を取得できませんでした。"
        )

        return 1

    latest_tweet = tweets[0]

    print(
        f"最新投稿ID: {latest_tweet['id']}"
    )

    print(
        f"最新投稿: {latest_tweet['text'][:100]}"
    )

    # --------------------------------------------------------
    # last_seen
    # --------------------------------------------------------

    last_seen = load_last_seen()

    if not last_seen:

        print(
            "初回実行です。"
        )

        print(
            "現在の最新投稿を基準点として保存します。"
        )

        save_last_seen(
            latest_tweet["id"]
        )

        print(
            "初回実行では通知を送信しません。"
        )

        return 0

    print(
        f"前回確認済みID: {last_seen}"
    )

    # --------------------------------------------------------
    # 新着投稿抽出
    # --------------------------------------------------------

    new_tweets = []

    last_seen_int = int(last_seen)

    for tweet in tweets:

        tweet_id_int = int(
            tweet["id"]
        )

        if tweet_id_int > last_seen_int:

            new_tweets.append(tweet)

    # 古い順に通知する
    new_tweets.sort(
        key=lambda x: int(x["id"])
    )

    if not new_tweets:

        print(
            "新着投稿はありません。"
        )

        return 0

    print(
        f"新着投稿: {len(new_tweets)}件"
    )

    # --------------------------------------------------------
    # Discord通知
    # --------------------------------------------------------

    last_success_id = last_seen

    for tweet in new_tweets:

        print("-" * 40)

        print(
            f"通知対象: {tweet['id']}"
        )

        print(
            tweet["text"][:200]
        )

        try:

            send_discord(tweet)

            # Discord送信成功後だけ更新
            last_success_id = tweet["id"]

            # 連続通知を少しだけ間隔を空ける
            time.sleep(1)

        except Exception as e:

            print(
                "Discord通知に失敗しました。"
            )

            print(
                f"詳細: {e}"
            )

            # 途中で失敗した場合、
            # 成功したところまでをlast_seenにする
            break

    # --------------------------------------------------------
    # 状態保存
    # --------------------------------------------------------

    if last_success_id != last_seen:

        save_last_seen(
            last_success_id
        )

    # すべて成功したか確認
    if last_success_id == new_tweets[-1]["id"]:

        print(
            "すべての新着投稿の処理が完了しました。"
        )

        return 0

    else:

        print(
            "一部の投稿が未処理です。"
        )

        return 1


# ============================================================
# 実行
# ============================================================

if __name__ == "__main__":

    try:

        exit_code = main()

    except KeyboardInterrupt:

        print(
            "処理を中断しました。"
        )

        exit_code = 1

    except Exception as e:

        print(
            "予期しないエラーが発生しました。"
        )

        print(
            f"詳細: {e}"
        )

        exit_code = 1

    raise SystemExit(exit_code)
