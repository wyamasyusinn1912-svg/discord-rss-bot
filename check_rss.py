import os
import re
import json
import time
import urllib.request
import urllib.error
import urllib.parse


# ============================================================
# 設定
# ============================================================

USERNAME = "StarWard_JP"

# 第1取得先：X公開Syndication
SYNDICATION_URL = (
    "https://syndication.twitter.com/"
    f"srv/timeline-profile/screen-name/{USERNAME}"
)

# 第2取得先：FxTwitter / FxEmbed
FX_PROFILE_URL = (
    "https://api.fxtwitter.com/2/profile/"
    f"{USERNAME}/media"
)

# 個別投稿取得
FX_STATUS_URL = (
    "https://api.fxtwitter.com/2/status"
)

LAST_SEEN_FILE = "last_seen.txt"

DISCORD_WEBHOOK = os.environ.get(
    "DISCORD_WEBHOOK"
)


# ============================================================
# 共通HTTP取得
# ============================================================

def http_get(url, timeout=30, retries=2):

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
                body = response.read()

                if status != 200:
                    raise RuntimeError(
                        f"HTTPステータス: {status}"
                    )

                return body

        except urllib.error.HTTPError as e:

            last_error = e

            print(
                f"HTTPエラー: {e.code} "
                f"(試行 {attempt}/{retries})"
            )

            if e.code == 429:

                print(
                    "429 Too Many Requests "
                    "→ この取得先は一時的に使用できません。"
                )

                # 429は長時間リトライしない
                if attempt < retries:

                    time.sleep(
                        10 * attempt
                    )

                    continue

                raise

            if e.code in (
                500,
                502,
                503,
                504,
            ):

                if attempt < retries:

                    time.sleep(
                        5 * attempt
                    )

                    continue

                raise

            raise

        except Exception as e:

            last_error = e

            print(
                f"通信エラー: {e}"
            )

            if attempt < retries:

                time.sleep(
                    3 * attempt
                )

                continue

            raise

    raise last_error


# ============================================================
# JSON取得
# ============================================================

def http_get_json(url):

    data = http_get(
        url,
        timeout=30,
        retries=2,
    )

    return json.loads(
        data.decode(
            "utf-8",
            errors="replace",
        )
    )


# ============================================================
# Syndicationから取得
# ============================================================

def fetch_syndication():

    print("")
    print("【取得方法1】X Syndication")
    print(
        f"URL: {SYNDICATION_URL}"
    )

    try:

        data = http_get(
            SYNDICATION_URL,
            timeout=30,
            retries=2,
        )

    except Exception as e:

        print(
            "Syndication取得失敗"
        )

        print(
            f"理由: {e}"
        )

        return []

    html_text = data.decode(
        "utf-8",
        errors="replace",
    )

    # __NEXT_DATA__を探す
    match = re.search(
        r'<script[^>]*id="__NEXT_DATA__"'
        r'[^>]*>(.*?)</script>',
        html_text,
        re.DOTALL,
    )

    if not match:

        print(
            "__NEXT_DATA__ が見つかりません。"
        )

        return []

    try:

        next_data = json.loads(
            match.group(1)
        )

    except Exception as e:

        print(
            f"JSON解析失敗: {e}"
        )

        return []

    entries = find_entries(
        next_data
    )

    if not entries:

        print(
            "timeline.entries が見つかりません。"
        )

        return []

    tweets = []

    for entry in entries:

        tweet = extract_tweet(
            entry
        )

        if tweet:

            tweets.append(
                tweet
            )

    tweets = unique_tweets(
        tweets
    )

    print(
        f"Syndication取得投稿数: "
        f"{len(tweets)}"
    )

    return tweets


# ============================================================
# timeline.entries探索
# ============================================================

def find_entries(obj):

    if isinstance(obj, dict):

        timeline = obj.get(
            "timeline"
        )

        if isinstance(
            timeline,
            dict,
        ):

            entries = timeline.get(
                "entries"
            )

            if isinstance(
                entries,
                list,
            ):

                return entries

        for value in obj.values():

            result = find_entries(
                value
            )

            if result is not None:

                return result

    elif isinstance(obj, list):

        for item in obj:

            result = find_entries(
                item
            )

            if result is not None:

                return result

    return None


# ============================================================
# Syndication投稿抽出
# ============================================================

def extract_tweet(entry):

    if not isinstance(
        entry,
        dict,
    ):
        return None

    content = entry.get(
        "content"
    )

    if not isinstance(
        content,
        dict,
    ):
        return None

    item_content = content.get(
        "itemContent"
    )

    if not isinstance(
        item_content,
        dict,
    ):
        return None

    tweet_results = (
        item_content.get(
            "tweet_results"
        )
    )

    result = None

    if isinstance(
        tweet_results,
        dict,
    ):

        result = tweet_results.get(
            "result"
        )

    # 古い形式
    if not isinstance(
        result,
        dict,
    ):

        result = item_content.get(
            "tweet"
        )

    if not isinstance(
        result,
        dict,
    ):
        return None

    legacy = result.get(
        "legacy"
    )

    if isinstance(
        legacy,
        dict,
    ):

        tweet_id = (
            legacy.get("id_str")
            or result.get("rest_id")
        )

        text = (
            legacy.get("full_text")
            or legacy.get("text")
            or ""
        )

        user = legacy.get(
            "user"
        )

        if not isinstance(
            user,
            dict,
        ):

            user = {}

        screen_name = (
            user.get(
                "screen_name"
            )
            or USERNAME
        )

        media_container = (
            legacy.get(
                "extended_entities"
            )
        )

    else:

        tweet_id = (
            result.get("id_str")
            or result.get("rest_id")
            or result.get("id")
        )

        text = (
            result.get("full_text")
            or result.get("text")
            or ""
        )

        user = result.get(
            "user"
        )

        if not isinstance(
            user,
            dict,
        ):

            user = {}

        screen_name = (
            user.get(
                "screen_name"
            )
            or USERNAME
        )

        media_container = (
            result.get(
                "extended_entities"
            )
        )

    if not tweet_id:
        return None

    if not str(tweet_id).isdigit():
        return None

    if not text:
        return None

    permalink = (
        f"https://x.com/"
        f"{screen_name}/status/"
        f"{tweet_id}"
    )

    media_urls = []

    if isinstance(
        media_container,
        dict,
    ):

        media_list = (
            media_container.get(
                "media"
            )
        )

        if isinstance(
            media_list,
            list,
        ):

            for media in media_list:

                if not isinstance(
                    media,
                    dict,
                ):
                    continue

                media_url = (
                    media.get(
                        "media_url_https"
                    )
                    or media.get(
                        "media_url"
                    )
                )

                if media_url:

                    media_urls.append(
                        media_url
                    )

    return {
        "id": str(tweet_id),
        "text": text,
        "screen_name": screen_name,
        "permalink": permalink,
        "media_urls": media_urls[:4],
    }


# ============================================================
# FxTwitterからメディア投稿を取得
# ============================================================

def fetch_fxtwitter_media():

    print("")
    print(
        "【取得方法2】FxTwitter / FxEmbed"
    )

    print(
        f"URL: {FX_PROFILE_URL}"
    )

    try:

        data = http_get_json(
            FX_PROFILE_URL
        )

    except Exception as e:

        print(
            "FxTwitter取得失敗"
        )

        print(
            f"理由: {e}"
        )

        return []

    results = data.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):

        print(
            "FxTwitterから投稿一覧を取得できませんでした。"
        )

        return []

    tweets = []

    for item in results:

        if not isinstance(
            item,
            dict,
        ):
            continue

        tweet_id = item.get(
            "id"
        )

        text = item.get(
            "text"
        )

        if not tweet_id:
            continue

        if not str(tweet_id).isdigit():
            continue

        if not text:
            continue

        author = item.get(
            "author"
        )

        if not isinstance(
            author,
            dict,
        ):

            author = {}

        screen_name = (
            author.get(
                "screen_name"
            )
            or USERNAME
        )

        permalink = (
            item.get(
                "url"
            )
            or
            f"https://x.com/"
            f"{screen_name}/status/"
            f"{tweet_id}"
        )

        media_urls = []

        media = item.get(
            "media"
        )

        if isinstance(
            media,
            dict,
        ):

            all_media = []

            for key in (
                "all",
                "photos",
            ):

                value = media.get(
                    key
                )

                if isinstance(
                    value,
                    list,
                ):

                    all_media.extend(
                        value
                    )

            for media_item in all_media:

                if not isinstance(
                    media_item,
                    dict,
                ):
                    continue

                url = (
                    media_item.get(
                        "url"
                    )
                    or media_item.get(
                        "thumbnail_url"
                    )
                )

                if url:
                    media_urls.append(
                        url
                    )

        tweets.append(
            {
                "id": str(tweet_id),
                "text": text,
                "screen_name": screen_name,
                "permalink": permalink,
                "media_urls": media_urls[:4],
            }
        )

    tweets = unique_tweets(
        tweets
    )

    print(
        f"FxTwitter取得投稿数: "
        f"{len(tweets)}"
    )

    return tweets


# ============================================================
# 投稿重複削除
# ============================================================

def unique_tweets(tweets):

    result = {}

    for tweet in tweets:

        tweet_id = tweet.get(
            "id"
        )

        if tweet_id:

            result[tweet_id] = tweet

    output = list(
        result.values()
    )

    output.sort(
        key=lambda x: int(
            x["id"]
        ),
        reverse=True,
    )

    return output


# ============================================================
# 個別投稿情報取得
# ============================================================

def fetch_single_tweet(
    tweet_id,
):

    url = (
        f"{FX_STATUS_URL}/"
        f"{USERNAME}/"
        f"{tweet_id}"
    )

    try:

        data = http_get_json(
            url
        )

    except Exception as e:

        print(
            f"個別投稿取得失敗: "
            f"{tweet_id}"
        )

        print(
            f"理由: {e}"
        )

        return None

    status = data.get(
        "status"
    )

    if not isinstance(
        status,
        dict,
    ):
        return None

    text = status.get(
        "text"
    )

    if not text:
        return None

    author = status.get(
        "author"
    )

    if not isinstance(
        author,
        dict,
    ):

        author = {}

    screen_name = (
        author.get(
            "screen_name"
        )
        or USERNAME
    )

    permalink = (
        status.get(
            "url"
        )
        or
        f"https://x.com/"
        f"{screen_name}/status/"
        f"{tweet_id}"
    )

    media_urls = []

    media = status.get(
        "media"
    )

    if isinstance(
        media,
        dict,
    ):

        for key in (
            "all",
            "photos",
        ):

            value = media.get(
                key
            )

            if isinstance(
                value,
                list,
            ):

                for media_item in value:

                    if not isinstance(
                        media_item,
                        dict,
                    ):
                        continue

                    url = (
                        media_item.get(
                            "url"
                        )
                        or media_item.get(
                            "thumbnail_url"
                        )
                    )

                    if url:

                        media_urls.append(
                            url
                        )

    return {
        "id": str(tweet_id),
        "text": text,
        "screen_name": screen_name,
        "permalink": permalink,
        "media_urls": media_urls[:4],
    }


# ============================================================
# last_seen.txt
# ============================================================

def load_last_seen():

    if not os.path.exists(
        LAST_SEEN_FILE
    ):

        print(
            "last_seen.txt がありません。"
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

    if value.isdigit():

        return value

    match = re.search(
        r"/status/(\d+)",
        value,
    )

    if match:

        return match.group(1)

    print(
        "last_seen.txt の値がX投稿IDではありません。"
    )

    return ""


def save_last_seen(
    tweet_id,
):

    with open(
        LAST_SEEN_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            str(tweet_id)
        )

    print(
        f"last_seen.txt更新: {tweet_id}"
    )


# ============================================================
# Discord送信
# ============================================================

def send_discord(
    tweet,
):

    if not DISCORD_WEBHOOK:

        raise RuntimeError(
            "DISCORD_WEBHOOK が設定されていません。"
        )

    content = (
        "🔔 **星の翼【公式】 新着投稿**\n\n"
        f"{tweet['text']}\n\n"
        f"🔗 {tweet['permalink']}"
    )

    payload = {
        "username": "非公式通知BOT",
        "content": content,
        "allowed_mentions": {
            "parse": []
        },
    }

    media_urls = tweet.get(
        "media_urls",
        [],
    )

    if media_urls:

        embeds = []

        for index, url in enumerate(
            media_urls[:4]
        ):

            if index == 0:

                embeds.append(
                    {
                        "image": {
                            "url": url
                        }
                    }
                )

            else:

                embeds.append(
                    {
                        "thumbnail": {
                            "url": url
                        }
                    }
                )

        payload["embeds"] = embeds

    data = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode(
        "utf-8"
    )

    request = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={
            "Content-Type":
                "application/json",
            "User-Agent":
                "StarWardDiscordBot/1.0",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            if response.status not in (
                200,
                204,
            ):

                raise RuntimeError(
                    "Discord HTTP "
                    f"{response.status}"
                )

    except urllib.error.HTTPError as e:

        body = e.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Discord通知失敗 "
            f"HTTP {e.code}: {body}"
        )

    print(
        "Discord通知成功"
    )


# ============================================================
# メイン
# ============================================================

def main():

    print("=" * 50)
    print("星の翼 X → Discord 通知BOT")
    print("=" * 50)

    if not DISCORD_WEBHOOK:

        print(
            "ERROR: DISCORD_WEBHOOK がありません。"
        )

        return 1

    # --------------------------------------------------------
    # 取得方法1
    # --------------------------------------------------------

    tweets = fetch_syndication()

    # --------------------------------------------------------
    # 取得方法1が429などで失敗した場合
    # 取得方法2を使用
    # --------------------------------------------------------

    if not tweets:

        print("")
        print(
            "Syndicationから投稿を取得できませんでした。"
        )

        print(
            "バックアップ取得先へ切り替えます。"
        )

        tweets = fetch_fxtwitter_media()

    # --------------------------------------------------------
    # どちらも失敗
    # --------------------------------------------------------

    if not tweets:

        print("")
        print(
            "ERROR: X投稿を取得できませんでした。"
        )

        print(
            "今回はlast_seen.txtを変更しません。"
        )

        return 1

    # --------------------------------------------------------
    # 最新投稿
    # --------------------------------------------------------

    latest = tweets[0]

    print("")
    print(
        f"取得投稿数: {len(tweets)}"
    )

    print(
        f"最新投稿ID: {latest['id']}"
    )

    print(
        f"最新投稿本文: "
        f"{latest['text'][:100]}"
    )

    # --------------------------------------------------------
    # last_seen
    # --------------------------------------------------------

    last_seen = load_last_seen()

    if not last_seen:

        print("")
        print(
            "初回実行です。"
        )

        save_last_seen(
            latest["id"]
        )

        print(
            "初回実行ではDiscord通知しません。"
        )

        return 0

    print(
        f"前回確認済みID: {last_seen}"
    )

    # --------------------------------------------------------
    # 新着投稿
    # --------------------------------------------------------

    last_seen_int = int(
        last_seen
    )

    new_tweets = []

    for tweet in tweets:

        try:

            tweet_id = int(
                tweet["id"]
            )

        except Exception:

            continue

        if tweet_id > last_seen_int:

            new_tweets.append(
                tweet
            )

    new_tweets.sort(
        key=lambda x: int(
            x["id"]
        )
    )

    # --------------------------------------------------------
    # 新着なし
    # --------------------------------------------------------

    if not new_tweets:

        print("")
        print(
            "新着投稿はありません。"
        )

        return 0

    print("")
    print(
        f"新着投稿: {len(new_tweets)}件"
    )

    # --------------------------------------------------------
    # Discord通知
    # --------------------------------------------------------

    last_success_id = last_seen

    for tweet in new_tweets:

        print("")
        print("-" * 50)

        print(
            f"通知対象ID: {tweet['id']}"
        )

        print(
            f"本文: {tweet['text'][:200]}"
        )

        # バックアップ取得で本文しか取れていない場合、
        # 個別投稿APIで画像などを補完
        if not tweet.get(
            "media_urls"
        ):

            detail = fetch_single_tweet(
                tweet["id"]
            )

            if detail:

                if detail.get(
                    "text"
                ):

                    tweet["text"] = (
                        detail["text"]
                    )

                if detail.get(
                    "media_urls"
                ):

                    tweet[
                        "media_urls"
                    ] = detail[
                        "media_urls"
                    ]

                if detail.get(
                    "permalink"
                ):

                    tweet[
                        "permalink"
                    ] = detail[
                        "permalink"
                    ]

        try:

            send_discord(
                tweet
            )

            last_success_id = (
                tweet["id"]
            )

            time.sleep(1)

        except Exception as e:

            print(
                "Discord通知に失敗しました。"
            )

            print(
                f"詳細: {e}"
            )

            break

    # --------------------------------------------------------
    # last_seen更新
    # --------------------------------------------------------

    if (
        last_success_id
        != last_seen
    ):

        save_last_seen(
            last_success_id
        )

    # --------------------------------------------------------
    # 完了判定
    # --------------------------------------------------------

    if (
        last_success_id
        == new_tweets[-1]["id"]
    ):

        print("")
        print(
            "すべての処理が完了しました。"
        )

        return 0

    print("")
    print(
        "一部の投稿が未処理です。"
    )

    return 1


# ============================================================
# 実行
# ============================================================

if __name__ == "__main__":

    try:

        result = main()

    except KeyboardInterrupt:

        print(
            "処理を中断しました。"
        )

        result = 1

    except Exception as e:

        print(
            "予期しないエラーが発生しました。"
        )

        print(
            f"詳細: {e}"
        )

        result = 1

    raise SystemExit(
        result
    )
