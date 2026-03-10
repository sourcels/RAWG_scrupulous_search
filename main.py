#!/usr/bin/env python3
import requests
import json
import sys
import os
from datetime import datetime

def _load_api_key() -> str:
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cred.txt")
    if not os.path.exists(cred_path):
        print("[ERROR] File cred.txt not found.")
        sys.exit(1)
    with open(cred_path, encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        print("[ERROR] File cred.txt is empty.")
        sys.exit(1)
    return key

RAWG_API_KEY = _load_api_key()
RAWG_BASE = "https://api.rawg.io/api"

GENRE_MAP = {
    "action":      "action",
    "adventure":   "adventure",
    "rpg":         "role-playing-games-rpg",
    "strategy":    "strategy",
    "puzzle":      "puzzle",
    "platformer":  "platformer",
    "racing":      "racing",
    "sports":      "sports",
    "simulation":  "simulation",
    "shooter":     "shooter",
    "indie":       "indie",
    "arcade":      "arcade",
    "fighting":    "fighting",
    "family":      "family",
    "card":        "card",
    "casual":      "casual",
    "educational": "educational",
    "horror":      "action",
}

PLATFORM_MAP = {
    "pc":              4,
    "playstation5":    187,
    "playstation4":    18,
    "xbox-one":        1,
    "xbox-series-x":   186,
    "nintendo-switch": 7,
    "ios":             3,
    "android":         21,
    "macos":           5,
    "linux":           6,
}

COOP_TAGS = ["co-op", "online-co-op", "local-co-op", "multiplayer", "online-multiplayer", "co-operative"]
SOLO_TAGS  = ["singleplayer", "single-player"]
VALID_SORTS = {"date_asc", "date_desc", "name_asc", "name_desc", "rating_asc", "rating_desc", "none"}


def parse_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    cfg = {
        "genres":    [],
        "platforms": [],
        "date_from": None,
        "date_to":   None,
        "coop":      "any",
        "rating":    0,
        "results":   20,
        "sort":      "date_asc",
    }

    with open(config_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            key   = key.strip().lower()
            value = value.strip()

            if key == "genre":
                cfg["genres"] = [g.strip().lower() for g in value.split(",") if g.strip()]

            elif key == "platform":
                cfg["platforms"] = [p.strip().lower() for p in value.split(",") if p.strip()]

            elif key == "date":
                parts = [p.strip() for p in value.split("-", 1)]
                if len(parts) == 2:
                    try:
                        cfg["date_from"] = datetime.strptime(parts[0].strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
                        cfg["date_to"]   = datetime.strptime(parts[1].strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
                    except ValueError as e:
                        print(f"[WARNING] Invalid data format: {value} -> {e}")

            elif key == "coop":
                val = value.lower()
                if val in ("true", "yes", "1"):
                    cfg["coop"] = True
                elif val in ("false", "no", "0"):
                    cfg["coop"] = False
                else:
                    cfg["coop"] = "any"

            elif key == "rating":
                try:
                    cfg["rating"] = float(value) if value else 0
                except ValueError:
                    cfg["rating"] = 0

            elif key == "results":
                try:
                    cfg["results"] = min(int(value), 200) if value else 20
                except ValueError:
                    cfg["results"] = 20

            elif key == "sort":
                val = value.lower()
                cfg["sort"] = val if val in VALID_SORTS else "date_asc"

    return cfg


def resolve_genre_ids(genre_names: list) -> tuple:
    slugs = []
    tags  = []
    for name in genre_names:
        if name in GENRE_MAP:
            slug = GENRE_MAP[name]
            if slug not in slugs:
                slugs.append(slug)
            if name == "horror":
                tags.append("horror")
        else:
            slugs.append(name)
    return slugs, tags


def sort_games(games: list, sort_mode: str) -> list:
    if sort_mode == "none":
        return games

    def date_key(g):
        raw = g.get("released") or ""
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return datetime.max

    def rating_key(g):
        return g.get("metacritic") or g.get("rating") or 0

    if sort_mode == "date_asc":
        return sorted(games, key=date_key)
    elif sort_mode == "date_desc":
        return sorted(games, key=date_key, reverse=True)
    elif sort_mode == "name_asc":
        return sorted(games, key=lambda g: (g.get("name") or "").lower())
    elif sort_mode == "name_desc":
        return sorted(games, key=lambda g: (g.get("name") or "").lower(), reverse=True)
    elif sort_mode == "rating_asc":
        return sorted(games, key=rating_key)
    elif sort_mode == "rating_desc":
        return sorted(games, key=rating_key, reverse=True)
    return games


def fetch_games(cfg: dict) -> list:
    genre_slugs, extra_tags = resolve_genre_ids(cfg["genres"])

    platform_ids = []
    for p in cfg["platforms"]:
        if p in PLATFORM_MAP:
            platform_ids.append(str(PLATFORM_MAP[p]))
        else:
            print(f"[WARNING] Unknown platform: {p} - skipped")

    coop_filter_tags = []
    if cfg["coop"] is True:
        coop_filter_tags = COOP_TAGS
    elif cfg["coop"] is False:
        coop_filter_tags = SOLO_TAGS

    sort_labels = {
        "date_asc":    "по дате (старые -> новые)",
        "date_desc":   "по дате (новые -> старые)",
        "name_asc":    "по названию А->Я",
        "name_desc":   "по названию Я->А",
        "rating_asc":  "по рейтингу (низкий -> высокий)",
        "rating_desc": "по рейтингу (высокий -> низкий)",
        "none":        "без сортировки",
    }

    print(f"\n Searching for games...")
    print(f"   Genre:       {', '.join(cfg['genres']) if cfg['genres'] else 'любые'}")
    print(f"   Platforms:   {', '.join(cfg['platforms']) if cfg['platforms'] else 'любые'}")
    print(f"   Date:        {cfg['date_from']} -> {cfg['date_to']}")
    coop_label = {True: "кооп/мульти", False: "одиночные", "any": "любой"}[cfg["coop"]]
    print(f"   Mode:       {coop_label}")
    if cfg["rating"] > 0:
        print(f"   Rating:     >= {cfg['rating']}")
    print(f"   Sorting:  {sort_labels.get(cfg['sort'], cfg['sort'])}")
    print()

    all_games = []
    page      = 1
    page_size = 40
    fetched   = 0
    need      = cfg["results"]

    while fetched < need:
        params = {
            "key":       RAWG_API_KEY,
            "page":      page,
            "page_size": min(page_size, need - fetched),
        }

        if genre_slugs:
            params["genres"] = ",".join(genre_slugs)
        if platform_ids:
            params["platforms"] = ",".join(platform_ids)
        if cfg["date_from"] and cfg["date_to"]:
            params["dates"] = f"{cfg['date_from']},{cfg['date_to']}"
        if cfg["rating"] > 0:
            params["metacritic"] = f"{int(cfg['rating'])},100"

        all_tags = extra_tags[:]
        if all_tags:
            params["tags"] = ",".join(all_tags)

        try:
            resp = requests.get(f"{RAWG_BASE}/games", params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[ERROR] Didn't fetch the data: {e}")
            break

        data    = resp.json()
        results = data.get("results", [])

        if not results:
            break

        for game in results:
            if coop_filter_tags:
                game_tags = [t["slug"] for t in game.get("tags", [])]
                if not any(ct in game_tags for ct in coop_filter_tags):
                    continue
            all_games.append(game)
            fetched += 1
            if fetched >= need:
                break

        if not data.get("next"):
            break

        page += 1

    all_games = sort_games(all_games, cfg["sort"])
    return all_games


def format_platforms(game: dict) -> str:
    platforms = game.get("platforms") or []
    return ", ".join(p["platform"]["name"] for p in platforms) if platforms else "-"


def format_genres(game: dict) -> str:
    genres = game.get("genres") or []
    return ", ".join(g["name"] for g in genres) if genres else "-"


def format_tags_short(game: dict, max_tags: int = 5) -> str:
    tags = game.get("tags") or []
    return ", ".join(t["name"] for t in tags[:max_tags]) if tags else "-"


def print_results(games: list, show_rating: bool = False):
    if not games:
        print("Games not found by your criteria.")
        return

    print(f"Games found: {len(games)}\n")
    print("=" * 80)

    for i, game in enumerate(games, 1):
        name        = game.get("name", "Unknown")
        released    = game.get("released") or "unknown"
        genres      = format_genres(game)
        platforms   = format_platforms(game)
        tags_short  = format_tags_short(game)
        metacritic  = game.get("metacritic")
        rawg_rating = game.get("rating", 0)
        slug        = game.get("slug", "")
        url         = f"https://rawg.io/games/{slug}" if slug else "-"

        print(f"[{i:>3}] {name}")
        print(f"       Date released: {released}")
        print(f"       Genre:       {genres}")
        print(f"       Platform(-s):   {platforms}")
        print(f"       Tag(-s):        {tags_short}")

        if show_rating:
            mc_str = str(metacritic) if metacritic else "н/д"
            print(f"       Metacritic:  {mc_str}   |   RAWG: {rawg_rating:.1f}/5")

        print(f"       Link:      {url}")
        print("-" * 80)


def save_results(games: list, out_path: str, show_rating: bool = False):
    output = []
    for game in games:
        entry = {
            "name":      game.get("name"),
            "released":  game.get("released"),
            "genres":    [g["name"] for g in (game.get("genres") or [])],
            "platforms": [p["platform"]["name"] for p in (game.get("platforms") or [])],
            "tags":      [t["name"] for t in (game.get("tags") or [])[:10]],
            "url":       f"https://rawg.io/games/{game.get('slug', '')}",
        }
        if show_rating:
            entry["metacritic"]  = game.get("metacritic")
            entry["rawg_rating"] = game.get("rating")
        output.append(entry)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults are saved in: {out_path}")


def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "search_config.txt")
    output_path = os.path.join(script_dir, "results.json")

    if RAWG_API_KEY == "YOUR_RAWG_API_KEY_HERE":
        print("RAWG_API_KEY is not specified!")
        print("   Get a free API key on https://rawg.io/apidocs")
        sys.exit(1)

    cfg = parse_config(config_path)
    show_rating = cfg["rating"] > 0

    games = fetch_games(cfg)
    print_results(games, show_rating=show_rating)
    save_results(games, output_path, show_rating=show_rating)


if __name__ == "__main__":
    main()