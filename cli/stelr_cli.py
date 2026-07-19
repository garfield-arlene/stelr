#!/usr/bin/env python3
"""Stelr CLI — manage your Stelr bookmarks from the command line."""

import argparse
import getpass
import json
import os
import sys
from urllib.parse import urlparse

import requests

CONFIG_DIR = os.path.expanduser("~/.stelr")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def require_config():
    config = load_config()
    if not config.get("server") or not config.get("token"):
        print("Not logged in. Run: stelr login <server-url>", file=sys.stderr)
        sys.exit(1)
    return config


def api_request(method, path, **kwargs):
    config = require_config()
    url = config["server"].rstrip("/") + path
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {config['token']}"
    try:
        resp = requests.request(method, url, headers=headers, timeout=15, **kwargs)
    except requests.exceptions.RequestException as e:
        print(f"Could not reach {config['server']}: {e}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 401:
        print("Your token is invalid or has been revoked. Run: stelr login <server-url>",
              file=sys.stderr)
        sys.exit(1)
    return resp


def _error(resp):
    try:
        return resp.json().get("error", resp.text)
    except ValueError:
        return resp.text


def _warn_if_insecure(server):
    parsed = urlparse(server)
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print(f"Warning: {server} uses plain HTTP, not HTTPS — your username, password, "
              "and API token will be sent unencrypted and can be read by anyone on the "
              "network path. Use an https:// URL unless this server really is your own "
              "machine.", file=sys.stderr)


def cmd_login(args):
    server = args.server.rstrip("/")
    _warn_if_insecure(server)
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    name = args.name or f"cli-{os.uname().nodename if hasattr(os, 'uname') else 'device'}"
    try:
        resp = requests.post(f"{server}/api/tokens",
                             json={"username": username, "password": password, "name": name},
                             timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"Could not reach {server}: {e}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 201:
        print(f"Login failed: {_error(resp)}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    save_config({"server": server, "token": data["token"], "username": username,
                "token_id": data["id"]})
    print(f"Logged in to {server} as {username}.")


def cmd_logout(args):
    config = load_config()
    if config.get("server") and config.get("token") and config.get("token_id"):
        try:
            requests.delete(f"{config['server'].rstrip('/')}/api/tokens/{config['token_id']}",
                           headers={"Authorization": f"Bearer {config['token']}"}, timeout=15)
        except requests.exceptions.RequestException:
            pass
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    print("Logged out.")


def cmd_whoami(args):
    config = load_config()
    if not config.get("server"):
        print("Not logged in.")
        return
    print(f"Server:   {config['server']}")
    print(f"Username: {config.get('username', '(unknown)')}")


def _find_group(name_or_id):
    """Return the group dict matching a name or id, or None."""
    groups = api_request("GET", "/api/groups").json()
    for g in groups:
        if g["id"] == name_or_id or g["name"] == name_or_id:
            return g
    return None


def cmd_add(args):
    group_id = ""
    if args.group:
        group = _find_group(args.group)
        if not group:
            print(f"Warning: group '{args.group}' not found; adding without a group.",
                  file=sys.stderr)
        else:
            group_id = group["id"]
    resp = api_request("POST", "/api/links",
                       json={"title": args.title, "url": args.url,
                             "rank": args.rank, "group_id": group_id})
    if resp.status_code != 201:
        print(f"Failed to add link: {_error(resp)}", file=sys.stderr)
        sys.exit(1)
    link = resp.json()
    print(f"Added '{link['title']}' (id={link['id']})")


def _print_links(links, group_names):
    for l in links:
        label = f" [{group_names.get(l['group_id'], '')}]" if l.get("group_id") else ""
        print(f"{l['rank']:>4}  {l['title']}{label}\n      {l['url']}\n      id: {l['id']}")


def cmd_list(args):
    params = {}
    if args.filter:
        params["q"] = args.filter
    if args.sort:
        params["sort"] = args.sort
        params["dir"] = args.dir

    groups = api_request("GET", "/api/groups").json()
    group_names = {g["id"]: g["name"] for g in groups}

    if args.group:
        group = _find_group(args.group)
        if not group:
            print(f"Group '{args.group}' not found.", file=sys.stderr)
            sys.exit(1)
        params["group"] = group["id"]

    links = api_request("GET", "/api/links", params=params).json()
    if not links:
        print("No links found.")
        return
    _print_links(links, group_names)


def cmd_update(args):
    payload = {}
    if args.title is not None:
        payload["title"] = args.title
    if args.url is not None:
        payload["url"] = args.url
    if args.rank is not None:
        payload["rank"] = args.rank
    if args.group is not None:
        if args.group == "":
            payload["group_id"] = ""
        else:
            group = _find_group(args.group)
            if not group:
                print(f"Group '{args.group}' not found.", file=sys.stderr)
                sys.exit(1)
            payload["group_id"] = group["id"]
    if not payload:
        print("Nothing to update — provide at least one of --title/--url/--rank/--group.",
              file=sys.stderr)
        sys.exit(1)
    resp = api_request("PUT", f"/api/links/{args.id}", json=payload)
    if resp.status_code != 200:
        print(f"Failed to update link: {_error(resp)}", file=sys.stderr)
        sys.exit(1)
    print(f"Updated link {args.id}.")


def cmd_delete(args):
    if not args.yes and input(f"Delete link {args.id}? [y/N] ").lower() != "y":
        print("Cancelled.")
        return
    resp = api_request("DELETE", f"/api/links/{args.id}")
    if resp.status_code != 200:
        print(f"Failed to delete link: {_error(resp)}", file=sys.stderr)
        sys.exit(1)
    print(f"Deleted link {args.id}.")


def cmd_groups(args):
    groups = api_request("GET", "/api/groups").json()
    if not groups:
        print("No groups.")
        return
    for g in groups:
        print(f"{g['name']}  (id: {g['id']})")


def cmd_group_create(args):
    resp = api_request("POST", "/api/groups", json={"name": args.name})
    if resp.status_code != 201:
        print(f"Failed to create group: {_error(resp)}", file=sys.stderr)
        sys.exit(1)
    print(f"Created group '{args.name}'.")


def cmd_group_delete(args):
    group = _find_group(args.name)
    if not group:
        print(f"Group '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    if not args.yes and input(
            f"Delete group '{args.name}'? Its links will become ungrouped. [y/N] ").lower() != "y":
        print("Cancelled.")
        return
    api_request("DELETE", f"/api/groups/{group['id']}")
    print(f"Deleted group '{args.name}'.")


def cmd_tokens(args):
    tokens = api_request("GET", "/api/tokens").json()
    if not tokens:
        print("No tokens.")
        return
    for t in tokens:
        print(f"{t['name']}  (id: {t['id']})")


def main():
    parser = argparse.ArgumentParser(
        prog="stelr", description="Manage your Stelr bookmarks from the command line.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="Log in to a Stelr server")
    p.add_argument("server", help="Server URL, e.g. http://localhost:8082")
    p.add_argument("--name", help="Name for this token (default: cli-<hostname>)")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("logout", help="Log out and revoke the local token")
    p.set_defaults(func=cmd_logout)

    p = sub.add_parser("whoami", help="Show current login")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("add", help="Add a link")
    p.add_argument("title")
    p.add_argument("url")
    p.add_argument("--rank", type=int, default=0)
    p.add_argument("--group", help="Group name or id")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="List links")
    p.add_argument("--filter", help="Keyword to match in title or URL")
    p.add_argument("--sort", choices=["rank", "title", "url"])
    p.add_argument("--dir", choices=["asc", "desc"], default="asc")
    p.add_argument("--group", help="Only show links in this group (name or id)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("update", help="Update a link")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--url")
    p.add_argument("--rank", type=int)
    p.add_argument("--group", help="Group name or id; pass an empty string to clear")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="Delete a link")
    p.add_argument("id")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("groups", help="List groups")
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("group-create", help="Create a group")
    p.add_argument("name")
    p.set_defaults(func=cmd_group_create)

    p = sub.add_parser("group-delete", help="Delete a group")
    p.add_argument("name", help="Group name or id")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p.set_defaults(func=cmd_group_delete)

    p = sub.add_parser("tokens", help="List API tokens for this account")
    p.set_defaults(func=cmd_tokens)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
