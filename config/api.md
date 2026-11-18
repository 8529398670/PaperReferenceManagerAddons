# Paper Reference Manager API

Every route this server answers, apart from the pages at /login/* and /join/*. Generated from the code by scripts/api_docs.sh: an app's own routes get their docs the same way, and a test fails until they do.

This file is generated: do not edit it. Change the docs next to the handlers and run `scripts/api_docs.sh`.

## Contents

- [Calling the API](#calling-the-api)
- [Errors](#errors)
- [Account](#account)
- [Sign-in](#sign-in)
- [API keys](#api-keys)
- [Admin](#admin)
- [Owner](#owner)
- [Monitoring](#monitoring)
- [Code and datasets](#code-and-datasets)
- [Content](#content)
- [Crawl](#crawl)
- [Figures](#figures)
- [Google Sheets](#google-sheets)
- [Library](#library)
- [Lists](#lists)
- [Missing papers](#missing-papers)
- [Missing pool](#missing-pool)
- [Research log](#research-log)
- [Review](#review)
- [Saved searches](#saved-searches)
- [Screener](#screener)
- [Summaries](#summaries)
- [Schemas](#schemas)

## Calling the API

| Way in | How |
|---|---|
| Browser session | A browser session. Its POSTs carry csrf_token in the body. The cookie's name is server.cookie_name, with the __Host- prefix while server.secure_cookies is on. |
| API key | An API key, as Authorization: Bearer <id>.<secret>. |

## Errors

An error reply is a JSON object whose `error` says what went wrong.

| Status | Meaning | Body |
|---|---|---|
| 400 | The request was refused as it stands. | [`Error`](#error) |
| 401 | Not signed in. | [`Error`](#error) |
| 403 | Not allowed, or a bad csrf_token. | [`Error`](#error) |
| 404 | No such thing, or this feature is switched off. | [`Error`](#error) |
| 409 | The record has moved on: an undo too late, or a stale edit. | [`Error`](#error) |
| 410 | It was deleted: a list in the trash, which can still be put back. | [`Error`](#error) |
| 429 | Too many requests. | [`Error`](#error) |
| 503 | In maintenance mode. Retry-After says when to try again. | [`Maintenance`](#maintenance) |

## Account

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/account/login-link`](#post-apiaccountlogin-link) | A login link for yourself | browser session or API key, anyone signed in |
| POST | [`/api/account/login-link/cancel`](#post-apiaccountlogin-linkcancel) | Stop your own login link working | browser session or API key, anyone signed in |
| POST | [`/api/account/rename`](#post-apiaccountrename) | Rename your account | browser session or API key, anyone signed in |
| GET | [`/api/account/sessions`](#get-apiaccountsessions) | Your signed-in devices | browser session or API key, anyone signed in |
| POST | [`/api/account/sessions/revoke-others`](#post-apiaccountsessionsrevoke-others) | Sign out every other device | browser session or API key, anyone signed in |
| POST | [`/api/account/sessions/{session_id}/label`](#post-apiaccountsessionssession_idlabel) | Name one of your devices | browser session or API key, anyone signed in |
| POST | [`/api/account/sessions/{session_id}/revoke`](#post-apiaccountsessionssession_idrevoke) | Sign out one of your devices | browser session or API key, anyone signed in |
| POST | [`/api/account/shortcuts`](#post-apiaccountshortcuts) | Change your keyboard shortcuts | browser session or API key, anyone signed in |
| POST | [`/api/account/tag-colors`](#post-apiaccounttag-colors) | Choose where your tag colours come from | browser session or API key, anyone signed in |
| POST | [`/api/account/theme`](#post-apiaccounttheme) | Pick your theme | browser session or API key, anyone signed in |
| POST | [`/api/account/themes`](#post-apiaccountthemes) | Replace your own themes | browser session or API key, anyone signed in |
| POST | [`/api/account/two-factor/confirm`](#post-apiaccounttwo-factorconfirm) | Turn two-factor on | browser session only, anyone signed in |
| POST | [`/api/account/two-factor/disable`](#post-apiaccounttwo-factordisable) | Turn two-factor off | browser session only, anyone signed in |
| POST | [`/api/account/two-factor/start`](#post-apiaccounttwo-factorstart) | Begin two-factor setup | browser session only, anyone signed in |
| POST | [`/api/bulk/account/sessions/revoke`](#post-apibulkaccountsessionsrevoke) | Sign out one of your devices, for many at once | browser session or API key, anyone signed in |
| GET | [`/api/language`](#get-apilanguage) | The UI's text | anyone |
| POST | [`/api/logout`](#post-apilogout) | Sign out | browser session or API key, anyone signed in |
| POST | [`/api/logs/events`](#post-apilogsevents) | Record what happened on the page | browser session or API key, anyone signed in |
| GET | [`/api/me`](#get-apime) | Who am I | browser session or API key, anyone signed in |
| GET | [`/api/team`](#get-apiteam) | List team | browser session or API key, anyone signed in |

### POST /api/account/login-link

A login link for yourself

A link that signs your own account in on a browser or another device. An API key may ask only if your account let it, from a browser session (POST /api/keys/{key_id}/sign-in); its link works once, for at most 15 minutes.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`create_my_login_link`](mcp.md#create_my_login_link) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expires_at` | string (date-time) or null | yes |  | null when it never expires. |
| `expires_in_seconds` | integer | yes |  | 0 when it never expires. |
| `login_path` | string | yes |  | Path of the login link. A credential: treat it like a password. |
| `max_uses` | integer | yes |  | 0 when unlimited. |
| `unlimited` | boolean | yes |  |  |

### POST /api/account/login-link/cancel

Stop your own login link working

Void your account's live login link without making a new one. Devices it already signed in stay signed in. Answers with removed: 0 or 1.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`cancel_my_login_link`](mcp.md#cancel_my_login_link) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `removed` | integer | yes |  | Links removed: 0 or 1. |

### POST /api/account/rename

Rename your account

Change your own display name (1-80 characters). expect, when given, is the name you think it has now; if someone changed it meanwhile the rename is refused with the current name, so nothing is overwritten unseen.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`rename_account`](mcp.md#rename_account) |
| Errors | 400, 401, 403, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `display_name` | string | yes | 1 to 80 characters |  |
| `expect` | string or null | no |  |  |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### GET /api/account/sessions

Your signed-in devices

Where your account is signed in, a page at a time: id, when it started and was last seen, the browser, and the name you gave it. Through an API key no device is current. next is the offset of the following page, or null on the last one.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_my_sessions`](mcp.md#list_my_sessions) |
| Errors | 400, 401, 403, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `sessions` | array of [`Session`](#session) | yes |  |  |
| `total` | integer | yes |  |  |

### POST /api/account/sessions/revoke-others

Sign out every other device

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`revoke_my_other_sessions`](mcp.md#revoke_my_other_sessions) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `removed` | integer | yes |  |  |

### POST /api/account/sessions/{session_id}/label

Name one of your devices

Give one of your devices a name (at most 80 characters; empty clears it). expect, when given, is the name you think it has now.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`label_my_session`](mcp.md#label_my_session) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `session_id` | path | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expect` | string or null | no |  | The name you think it has. Answers 409 if it has another. |
| `label` | string | yes | at most 80 characters | At most 80 characters. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `label` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/account/sessions/{session_id}/revoke

Sign out one of your devices

End one of your signed-in sessions; that browser has to sign in again.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`revoke_my_session`](mcp.md#revoke_my_session) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `session_id` | path | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/account/shortcuts

Change your keyboard shortcuts

Replace your changed keyboard shortcuts: action name to binding, such as "search": "Mod+K" (Mod is Cmd on a Mac, Ctrl elsewhere). Send the whole set; an empty binding switches a key off, and {} puts every key back to its default.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_shortcuts`](mcp.md#set_shortcuts) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `shortcuts` | map of string | yes |  | Action name to binding, such as "search": "Mod+K". Mod is Cmd on a Mac and Ctrl elsewhere. Only changed shortcuts are listed; an empty binding switches that key off. Replaces the whole set; {} puts every key back to its default. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `shortcuts` | map of string | yes |  |  |

### POST /api/account/tag-colors

Choose where your tag colours come from

Tags on lists are coloured from Wright State's palette (wsu), or from a gradient of the theme you use (theme). Only how you see them: what a list stores is unchanged.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_tag_colors`](mcp.md#set_tag_colors) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `mode` | string | yes | one of `wsu`, `theme` | wsu: Wright State's palette (the default). theme: a gradient from the accent to the second colour of the theme you use. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `mode` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/account/theme

Pick your theme

Switch to another theme from your list (or the defaults), by its id.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_theme`](mcp.md#set_theme) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `theme_id` | string | yes |  | A theme's id. Empty for the first in the list. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `theme_id` | string | yes |  |  |

### POST /api/account/themes

Replace your own themes

Replace your whole list of color themes (1 to 40) and pick the one you use. themes: null goes back to following the app's defaults. A theme is the Theme schema in the API reference (config/api.json): id, name, mode light|dark, accent, second, and optional colors as #rrggbb.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_themes`](mcp.md#set_themes) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | no |  | Which built-in themes this list has seen: the highest since in Theme.builtIn (static/js/theme.js) when it was saved. Built-in themes added after that join the list the browser shows. Left out: 0, the first ones. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `theme_id` | string | no |  | The theme you use. |
| `themes` | array of [`Theme`](#theme) or null | no |  | Your whole list, 1 to 40 themes. null goes back to following the app's defaults. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `theme_id` | string | yes |  |  |
| `themes` | array of [`Theme`](#theme) or null | yes |  | What you now see; null while the built-in themes apply. |
| `themes_builtins` | integer | yes |  | Which built-in themes that list has seen (see builtins on POST /api/account/themes). |
| `themes_custom` | boolean | yes |  |  |

### POST /api/account/two-factor/confirm

Turn two-factor on

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `code` | string | yes |  |  |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `recovery_codes` | array of string | yes |  |  |

### POST /api/account/two-factor/disable

Turn two-factor off

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `code` | string | yes |  |  |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/account/two-factor/start

Begin two-factor setup

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `secret` | string | yes |  |  |

### POST /api/bulk/account/sessions/revoke

Sign out one of your devices, for many at once

Runs POST /api/account/sessions/{session_id}/revoke once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`revoke_my_session_bulk`](mcp.md#revoke_my_session_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### GET /api/language

The UI's text

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 429, 503 |

**Reply 200**: Success

An empty object.

### POST /api/logout

Sign out

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Ends a browser session; a key has none to end. |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/logs/events

Record what happened on the page

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The browser's own activity reports (track.js), not an action. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `events` | array of object | yes |  |  |
| `tab` | string | yes |  |  |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `accepted` | integer | yes |  |  |

### GET /api/me

Who am I

The account this API key belongs to, the role it acts with (role -- never higher than the key's own scope), and the account's own role.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`whoami`](mcp.md#whoami) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`Me`](#me).

### GET /api/team

List team

People with an active account, a page at a time: id and display name.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_team`](mcp.md#list_team) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `members` | array of [`Member`](#member) | yes |  |  |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |

## Sign-in

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/login`](#post-apilogin) | Redeem a login link | anyone |
| POST | [`/api/login/two-factor`](#post-apilogintwo-factor) | Finish a sign-in with a code | anyone |

### POST /api/login

Redeem a login link

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 400, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `credential` | string | yes |  |  |

**Reply 200**: Success

[`SignIn`](#signin).

### POST /api/login/two-factor

Finish a sign-in with a code

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 400, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `challenge` | string | yes |  |  |
| `code` | string | yes |  |  |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

## API keys

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/admin/keys`](#get-apiadminkeys) | Every key in the app | browser session only, admins |
| POST | [`/api/admin/keys`](#post-apiadminkeys) | Create a key that acts as someone else | browser session only, admins |
| POST | [`/api/admin/keys/{key_id}/delete`](#post-apiadminkeyskey_iddelete) | Delete anyone's key | browser session only, admins |
| POST | [`/api/admin/keys/{key_id}/expiry`](#post-apiadminkeyskey_idexpiry) | Change when anyone's key expires | browser session only, admins |
| POST | [`/api/admin/keys/{key_id}/rename`](#post-apiadminkeyskey_idrename) | Rename anyone's key | browser session only, admins |
| POST | [`/api/admin/keys/{key_id}/restore`](#post-apiadminkeyskey_idrestore) | Undo deleting anyone's key | browser session only, admins |
| POST | [`/api/admin/keys/{key_id}/revoke`](#post-apiadminkeyskey_idrevoke) | Revoke anyone's key | browser session only, admins |
| GET | [`/api/keys`](#get-apikeys) | Your API keys | browser session only, anyone signed in |
| POST | [`/api/keys`](#post-apikeys) | Create an API key | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/delete`](#post-apikeyskey_iddelete) | Delete one of your keys | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/expiry`](#post-apikeyskey_idexpiry) | Change when one of your keys expires | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/rename`](#post-apikeyskey_idrename) | Rename one of your keys | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/restore`](#post-apikeyskey_idrestore) | Undo deleting one of your keys | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/revoke`](#post-apikeyskey_idrevoke) | Revoke one of your keys | browser session only, anyone signed in |
| POST | [`/api/keys/{key_id}/sign-in`](#post-apikeyskey_idsign-in) | Let one of your keys make sign-in links | browser session only, anyone signed in |

### GET /api/admin/keys

Every key in the app

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `q` | query | string | no |  | Keep keys whose name or owner contains this, in any case. |
| `live` | query | string | no | one of `true` | Leave out revoked and expired keys. |
| `sort` | query | string | no | one of `display_name`, `name`, `role`, `last_used_at`, `expires_at`, `created_at` | Field to sort the whole list by. Rows without it go last. |
| `dir` | query | string | no | one of `asc`, `desc` | Default asc. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `keys` | array of [`APIKey`](#apikey) | yes |  |  |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |

### POST /api/admin/keys

Create a key that acts as someone else

Any admin may do this for an ordinary user, and only the owner for another admin. Nobody may do it for the owner. The key records who made it and shows that to the person it acts as.

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_days` | integer or null | no | 0 to 3650 | Absent or null: the configured default. 0: never expires. |
| `name` | string | yes | 1 to 80 characters |  |
| `role` | string | no | one of `admin`, `user`; default `user` |  |
| `user_id` | integer | yes | at least 1 |  |

**Reply 201**: Success

[`NewAPIKey`](#newapikey).

### POST /api/admin/keys/{key_id}/delete

Delete anyone's key

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/admin/keys/{key_id}/expiry

Change when anyone's key expires

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_days` | integer | yes | 0 to 3650 | Counted from now. 0 means it never expires. |

**Reply 200**: Success

[`APIKey`](#apikey).

### POST /api/admin/keys/{key_id}/rename

Rename anyone's key

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expect` | string or null | no |  | The name you think it has. Answers 409 if it has another. |
| `name` | string | yes | 1 to 80 characters | 1-80 characters. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `name` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/admin/keys/{key_id}/restore

Undo deleting anyone's key

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`APIKey`](#apikey).

### POST /api/admin/keys/{key_id}/revoke

Revoke anyone's key

|  |  |
|---|---|
| Who may call | browser session only, admins |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### GET /api/keys

Your API keys

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `q` | query | string | no |  | Keep keys whose name contains this, in any case. |
| `live` | query | string | no | one of `true` | Leave out revoked and expired keys. |
| `sort` | query | string | no | one of `name`, `role`, `last_used_at`, `expires_at`, `created_at` | Field to sort the whole list by. Rows without it go last. |
| `dir` | query | string | no | one of `asc`, `desc` | Default asc. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `keys` | array of [`APIKey`](#apikey) | yes |  |  |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |

### POST /api/keys

Create an API key

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_days` | integer or null | no | 0 to 3650 | Absent or null: the configured default. 0: never expires. |
| `name` | string | yes | 1 to 80 characters |  |
| `role` | string | no | one of `admin`, `user`; default `user` |  |

**Reply 201**: Success

[`NewAPIKey`](#newapikey).

### POST /api/keys/{key_id}/delete

Delete one of your keys

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/keys/{key_id}/expiry

Change when one of your keys expires

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_days` | integer | yes | 0 to 3650 | Counted from now. 0 means it never expires. |

**Reply 200**: Success

[`APIKey`](#apikey).

### POST /api/keys/{key_id}/rename

Rename one of your keys

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expect` | string or null | no |  | The name you think it has. Answers 409 if it has another. |
| `name` | string | yes | 1 to 80 characters | 1-80 characters. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `name` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/keys/{key_id}/restore

Undo deleting one of your keys

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`APIKey`](#apikey).

### POST /api/keys/{key_id}/revoke

Revoke one of your keys

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/keys/{key_id}/sign-in

Let one of your keys make sign-in links

Off by default. When on, the key may ask POST /api/account/login-link for a link that signs your account in on a browser, which then can do everything you can, including what keys may not. The link works once, for at most 15 minutes.

|  |  |
|---|---|
| Who may call | browser session only, anyone signed in |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key_id` | path | string | yes |  | The key's id, from GET /api/keys (GET /api/admin/keys for anyone's). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `may_sign_in` | boolean | yes |  | true lets the key make a login link for your account: one that works once, for at most 15 minutes. |

**Reply 200**: Success

[`APIKey`](#apikey).

## Admin

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/admin/theme-defaults`](#get-apiadmintheme-defaults) | Default themes | browser session or API key, admins |
| POST | [`/api/admin/theme-defaults`](#post-apiadmintheme-defaults) | Replace the default themes | browser session or API key, admins |
| GET | [`/api/admin/users`](#get-apiadminusers) | List users | browser session or API key, admins |
| POST | [`/api/admin/users`](#post-apiadminusers) | Create an account | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/cancel-login-link`](#post-apiadminusersuser_idcancel-login-link) | Stop an account's login link working | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/delete`](#post-apiadminusersuser_iddelete) | Delete an account | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/disabled`](#post-apiadminusersuser_iddisabled) | Disable or enable a user | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/reissue-login`](#post-apiadminusersuser_idreissue-login) | A new login link for an account | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/rename`](#post-apiadminusersuser_idrename) | Rename someone | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/reset-two-factor`](#post-apiadminusersuser_idreset-two-factor) | Turn off an account's two-factor | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/revoke-access`](#post-apiadminusersuser_idrevoke-access) | Revoke a user's access | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/role`](#post-apiadminusersuser_idrole) | Change an account's role | browser session or API key, admins |
| GET | [`/api/admin/users/{user_id}/sessions`](#get-apiadminusersuser_idsessions) | An account's signed-in devices | browser session or API key, admins |
| POST | [`/api/admin/users/{user_id}/sessions/{session_id}/revoke`](#post-apiadminusersuser_idsessionssession_idrevoke) | Sign out one of an account's devices | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/cancel-login-link`](#post-apibulkadminuserscancel-login-link) | Stop an account's login link working, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/delete`](#post-apibulkadminusersdelete) | Delete an account, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/disabled`](#post-apibulkadminusersdisabled) | Disable or enable a user, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/reset-two-factor`](#post-apibulkadminusersreset-two-factor) | Turn off an account's two-factor, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/revoke-access`](#post-apibulkadminusersrevoke-access) | Revoke a user's access, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/role`](#post-apibulkadminusersrole) | Change an account's role, for many at once | browser session or API key, admins |
| POST | [`/api/bulk/admin/users/sessions/revoke`](#post-apibulkadminuserssessionsrevoke) | Sign out one of an account's devices, for many at once | browser session or API key, admins |

### GET /api/admin/theme-defaults

Default themes

The theme list everyone without their own list sees. themes is null while the built-in ones apply.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_get_theme_defaults`](mcp.md#admin_get_theme_defaults) |
| Errors | 401, 403, 404, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | yes |  | Which built-in themes that list has seen (see builtins on POST /api/account/themes). |
| `themes` | array of [`Theme`](#theme) or null | yes |  | null while the built-in themes apply. |

### POST /api/admin/theme-defaults

Replace the default themes

Replace the theme list everyone without their own list sees, 1 to 40 themes in the Theme schema of the API reference. null puts the built-in themes back.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_set_theme_defaults`](mcp.md#admin_set_theme_defaults) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | no |  | Which built-in themes this list has seen: the highest since in Theme.builtIn (static/js/theme.js) when it was saved. Built-in themes added after that join the list the browser shows. Left out: 0, the first ones. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `themes` | array of [`Theme`](#theme) or null | no |  | 1 to 40 themes. null goes back to the built-in ones. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | yes |  | Which built-in themes that list has seen (see builtins on POST /api/account/themes). |
| `ok` | boolean | yes |  |  |
| `themes` | array of [`Theme`](#theme) or null | yes |  |  |

### GET /api/admin/users

List users

Accounts, a page at a time, including disabled ones, with each one's role and which is the owner. next is the offset of the following page, or null on the last one.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_list_users`](mcp.md#admin_list_users) |
| Errors | 400, 401, 403, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `q` | query | string | no |  | Keep accounts whose name or username contains this, in any case. |
| `sort` | query | string | no | one of `display_name`, `role`, `disabled`, `created_at` | Field to sort the whole list by. Rows without it go last. |
| `dir` | query | string | no | one of `asc`, `desc` | Default asc. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |
| `users` | array of [`User`](#user) | yes |  |  |

### POST /api/admin/users

Create an account

Make a new account and its first login link, to hand to the person. role is admin or user. Answers with user_id and the link.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_create_user`](mcp.md#admin_create_user) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `display_name` | string | yes | 1 to 80 characters |  |
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |
| `role` | string | yes | one of `admin`, `user` |  |

**Reply 201**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expires_at` | string (date-time) or null | yes |  | null when it never expires. |
| `expires_in_seconds` | integer | yes |  | 0 when it never expires. |
| `login_path` | string | yes |  | Path of the login link. A credential: treat it like a password. |
| `max_uses` | integer | yes |  | 0 when unlimited. |
| `unlimited` | boolean | yes |  |  |
| `user_id` | integer | yes |  |  |

### POST /api/admin/users/{user_id}/cancel-login-link

Stop an account's login link working

Void an account's live login link without making a new one: a link that went somewhere it should not have.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_cancel_login_link`](mcp.md#admin_cancel_login_link) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `removed` | integer | yes |  | Links removed: 0 or 1. |

### POST /api/admin/users/{user_id}/delete

Delete an account

Remove an account for good, with its sessions, login link and API keys.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_delete_user`](mcp.md#admin_delete_user) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `removed` | [`Revoked`](#revoked) | yes |  |  |

### POST /api/admin/users/{user_id}/disabled

Disable or enable a user

Switch an account off (disabled: true) or back on (false). Disabling signs it out everywhere and voids its live login link; its API keys stop working while it is off. Reversible. The owner and your own account cannot be disabled.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_set_user_disabled`](mcp.md#admin_set_user_disabled) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `disabled` | boolean | yes |  |  |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/admin/users/{user_id}/reissue-login

A new login link for an account

For someone who lost their device or their link: a fresh login link for their account.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_reissue_login`](mcp.md#admin_reissue_login) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expires_at` | string (date-time) or null | yes |  | null when it never expires. |
| `expires_in_seconds` | integer | yes |  | 0 when it never expires. |
| `login_path` | string | yes |  | Path of the login link. A credential: treat it like a password. |
| `max_uses` | integer | yes |  | 0 when unlimited. |
| `unlimited` | boolean | yes |  |  |

### POST /api/admin/users/{user_id}/rename

Rename someone

Change another account's display name (1-80 characters). Only the owner renames an admin. expect, when given, is the name you think it has now; if it changed meanwhile the rename is refused with the current name.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_rename_user`](mcp.md#admin_rename_user) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `display_name` | string | yes | 1 to 80 characters | 1-80 characters. |
| `expect` | string or null | no |  | The name you think they have. Answers 409 if it is another. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/admin/users/{user_id}/reset-two-factor

Turn off an account's two-factor

For someone who lost both their phone and their recovery codes: switches their two-factor sign-in off so a login link lets them in again. Only the owner resets an admin's; the owner's is reset from a shell.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_reset_two_factor`](mcp.md#admin_reset_two_factor) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/admin/users/{user_id}/revoke-access

Revoke a user's access

For an account that may be compromised: ends every session and voids its live login link and every API key it holds, at once.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_revoke_access`](mcp.md#admin_revoke_access) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `revoked` | [`Revoked`](#revoked) | yes |  |  |

### POST /api/admin/users/{user_id}/role

Change an account's role

Make an account an admin or an ordinary user. Only the owner takes an admin's rights away; the owner is always an admin, and nobody changes their own role. Becoming an admin ends the account's sessions and live login link.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_set_user_role`](mcp.md#admin_set_user_role) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `role` | string | yes | one of `admin`, `user` |  |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |
| `role` | string | yes |  |  |

### GET /api/admin/users/{user_id}/sessions

An account's signed-in devices

Where an account is signed in: every session, with when it started and was last seen. Addresses are shown to the owner only, and only the owner sees the owner's.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_list_user_sessions`](mcp.md#admin_list_user_sessions) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `sessions` | array of [`Session`](#session) | yes |  |  |
| `total` | integer | yes |  |  |

### POST /api/admin/users/{user_id}/sessions/{session_id}/revoke

Sign out one of an account's devices

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_revoke_user_session`](mcp.md#admin_revoke_user_session) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `user_id` | path | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `session_id` | path | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### POST /api/bulk/admin/users/cancel-login-link

Stop an account's login link working, for many at once

Runs POST /api/admin/users/{user_id}/cancel-login-link once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_cancel_login_link_bulk`](mcp.md#admin_cancel_login_link_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/delete

Delete an account, for many at once

Runs POST /api/admin/users/{user_id}/delete once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_delete_user_bulk`](mcp.md#admin_delete_user_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/disabled

Disable or enable a user, for many at once

Runs POST /api/admin/users/{user_id}/disabled once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_set_user_disabled_bulk`](mcp.md#admin_set_user_disabled_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].disabled` | boolean | no |  |  |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |
| `shared.disabled` | boolean | no |  |  |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/reset-two-factor

Turn off an account's two-factor, for many at once

Runs POST /api/admin/users/{user_id}/reset-two-factor once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_reset_two_factor_bulk`](mcp.md#admin_reset_two_factor_bulk) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/revoke-access

Revoke a user's access, for many at once

Runs POST /api/admin/users/{user_id}/revoke-access once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_revoke_access_bulk`](mcp.md#admin_revoke_access_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/role

Change an account's role, for many at once

Runs POST /api/admin/users/{user_id}/role once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_set_user_role_bulk`](mcp.md#admin_set_user_role_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].role` | string | no | one of `admin`, `user` |  |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |
| `shared.role` | string | no | one of `admin`, `user` |  |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

### POST /api/bulk/admin/users/sessions/revoke

Sign out one of an account's devices, for many at once

Runs POST /api/admin/users/{user_id}/sessions/{session_id}/revoke once per item: items holds each one's id and fields, shared the fields they have in common (an item's own win). Each runs as that route would, in order, and one failing does not stop the rest; the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`admin_revoke_user_session_bulk`](mcp.md#admin_revoke_user_session_bulk) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

**Reply 200**: Success

[`BulkReply`](#bulkreply).

## Owner

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/owner/jobs`](#get-apiownerjobs) | Background jobs | browser session only, the owner |
| POST | [`/api/owner/jobs/{name}/run`](#post-apiownerjobsnamerun) | Run a job now | browser session only, the owner |
| GET | [`/api/owner/logs/days`](#get-apiownerlogsdays) | The days on record | browser session only, the owner |
| GET | [`/api/owner/logs/days/{date}`](#get-apiownerlogsdaysdate) | One day's entries | browser session only, the owner |
| POST | [`/api/owner/logs/days/{date}/delete`](#post-apiownerlogsdaysdatedelete) | Delete one day | browser session only, the owner |
| GET | [`/api/owner/logs/days/{date}/download`](#get-apiownerlogsdaysdatedownload) | One day's entries as a file | browser session only, the owner |
| GET | [`/api/owner/logs/ip-names`](#get-apiownerlogsip-names) | What the owner calls addresses | browser session only, the owner |
| POST | [`/api/owner/logs/ip-names`](#post-apiownerlogsip-names) | Name an address or a range, or rename one | browser session only, the owner |
| POST | [`/api/owner/logs/ip-names/delete`](#post-apiownerlogsip-namesdelete) | Take a name off an address or a range | browser session only, the owner |
| POST | [`/api/owner/logs/prune`](#post-apiownerlogsprune) | Apply the retention rules now | browser session only, the owner |
| GET | [`/api/owner/logs/stream`](#get-apiownerlogsstream) | New log entries as they happen | browser session only, the owner |
| GET | [`/api/owner/settings`](#get-apiownersettings) | config.yaml, as a form | browser session only, the owner |
| POST | [`/api/owner/settings`](#post-apiownersettings) | Save settings | browser session only, the owner |

### GET /api/owner/jobs

Background jobs

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 404, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `jobs` | array of [`Job`](#job) | yes |  |  |

### POST /api/owner/jobs/{name}/run

Run a job now

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `name` | path | string | yes |  | The job's name, from GET /api/owner/jobs. |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 202**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### GET /api/owner/logs/days

The days on record

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `q` | query | string | no |  | The Logs screen's search. |

**Reply 200**: Success

[`LogDays`](#logdays).

### GET /api/owner/logs/days/{date}

One day's entries

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `date` | path | string | yes |  | The day's date, from GET /api/owner/logs/days. |
| `q` | query | string | no |  | The Logs screen's search. |
| `before` | query | integer or null | no | at least 0 |  |
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |

**Reply 200**: Success

[`LogDay`](#logday).

### POST /api/owner/logs/days/{date}/delete

Delete one day

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `date` | path | string | yes |  | The day's date, from GET /api/owner/logs/days. |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `deleted` | boolean | yes |  |  |

### GET /api/owner/logs/days/{date}/download

One day's entries as a file

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `date` | path | string | yes |  | The day's date, from GET /api/owner/logs/days. |

**Reply 200**: Success

Text, as `application/x-ndjson`.

### GET /api/owner/logs/ip-names

What the owner calls addresses

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 403, 404, 429, 503 |

**Reply 200**: Success

[`IPNames`](#ipnames).

### POST /api/owner/logs/ip-names

Name an address or a range, or rename one

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `name` | string | yes | 1 to 80 characters |  |
| `target` | string | yes | e.g. `10.0.0.0/24` | An address, or a range such as 10.0.0.0/24. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `name` | string | yes |  |  |
| `target` | string | yes |  |  |

### POST /api/owner/logs/ip-names/delete

Take a name off an address or a range

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `target` | string | yes | e.g. `10.0.0.0/24` | An address, or a range such as 10.0.0.0/24. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `deleted` | boolean | yes |  |  |

### POST /api/owner/logs/prune

Apply the retention rules now

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`PruneResult`](#pruneresult).

### GET /api/owner/logs/stream

New log entries as they happen

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `q` | query | string | no |  | The Logs screen's search. |

**Reply 200**: Success

Text, as `text/event-stream`.

### GET /api/owner/settings

config.yaml, as a form

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 404, 429, 503 |

**Reply 200**: Success

[`SettingsSnapshot`](#settingssnapshot).

### POST /api/owner/settings

Save settings

|  |  |
|---|---|
| Who may call | browser session only, the owner |
| Errors | 400, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changes` | object | yes |  | Setting paths and their new values. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `version` | string | yes |  |  |

**Reply 200**: Success

[`SettingsResult`](#settingsresult).

## Monitoring

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/api.json`](#get-apiapijson) | This document | browser session or API key, anyone signed in |
| GET | [`/api/health`](#get-apihealth) | Is the process up | anyone |
| GET | [`/api/mcp.json`](#get-apimcpjson) | The MCP tools: every tool /mcp has, its arguments, and the route it stands for | browser session or API key, anyone signed in |
| GET | [`/api/ready`](#get-apiready) | Can the server do real work | anyone |
| GET | [`/mcp`](#get-mcp) | Refused: this server has no stream | anyone |
| POST | [`/mcp`](#post-mcp) | Model Context Protocol, at the key's role | API key only, anyone signed in |
| DELETE | [`/mcp`](#delete-mcp) | Refused: this server keeps no sessions | anyone |

### GET /api/api.json

This document

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The API reference itself; GET /api/mcp.json is the MCP one. |
| Errors | 401, 404, 429, 503 |

**Reply 200**: Success

An empty object.

### GET /api/health

Is the process up

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### GET /api/mcp.json

The MCP tools: every tool /mcp has, its arguments, and the route it stands for

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The MCP reference itself; tools/list gives the same list. |
| Errors | 401, 404, 429, 503 |

**Reply 200**: Success

An empty object.

### GET /api/ready

Can the server do real work

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

### GET /mcp

Refused: this server has no stream

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 404, 429, 503 |

**Reply 405**: Success

### POST /mcp

Model Context Protocol, at the key's role

|  |  |
|---|---|
| Who may call | API key only, anyone signed in |
| MCP tool | None, HTTP only: The MCP endpoint itself. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

An empty object.

**Reply 200**: Success

An empty object.

### DELETE /mcp

Refused: this server keeps no sessions

|  |  |
|---|---|
| Who may call | anyone |
| Errors | 404, 429, 503 |

**Reply 405**: Success

## Code and datasets

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/code`](#get-apicode) | Every paper that ships code | browser session or API key, anyone signed in |
| GET | [`/api/datasets`](#get-apidatasets) | What public data the library stands on | browser session or API key, anyone signed in |
| POST | [`/api/export/xlsx`](#post-apiexportxlsx) | A table as an Excel workbook | browser session or API key, anyone signed in |

### GET /api/code

Every paper that ships code

One row per paper whose text links a code host, with each repository as GitHub or OSF describe it, the methods its README confirms or its citing papers suggest, and where the paper is curated.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_code`](mcp.md#list_code) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `enrich` | map of boolean | yes |  | github, osf: whether a token is set (without one that host is not asked). |
| `papers` | array of object | yes |  | One per paper that links code: key, title, year, doi, journal, added, cites (OpenAlex), mods, lists (slug, name, position), tiers (slug, name, tier, color), figs (figures picked), and code: url, host, where, repo, info (GitHub or OSF: status, description, stars, language, methods), inferred (methods of the papers linking it), repaired (url, tier, confidence, original) for a link the PDF text mangled. |

### GET /api/datasets

What public data the library stands on

One row per paper that links a data archive record or names a public collection (HCP, NSD, ...), each record with what its archive says it is. The Datasets screen also groups these by dataset.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_datasets`](mcp.md#list_datasets) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `papers` | array of object | yes |  | One per paper that links data or names a public collection: key, title, year, doi, added, cites, mods, lists, tiers, figs, code_n, data (url, host, where, accession when recovered from a bare ds number, target, info: status, title, description), names (name, url, description). |

### POST /api/export/xlsx

A table as an Excel workbook

Turns the tables a screen is showing into one .xlsx: a sheet each, the header frozen and bold, links clickable. The screens send exactly the rows they show, in their order.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download, made from the rows sent. |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `filename` | string | no | default `export` | The download's name, without .xlsx. |
| `sheets` | array of object | yes |  | The sheets, in order. At most 8. |
| `sheets[].columns` | array of string | yes |  | The header row. |
| `sheets[].name` | string | yes |  | The sheet's tab name (31 characters at most; cut to fit). |
| `sheets[].rows` | array of array of any | yes |  | The rows: text, numbers, or null. A cell that is an http(s) URL becomes a link. |

**Reply 200**: Success

Text, as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## Content

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/content/papers`](#get-apicontentpapers) | The papers a stage has not finished | browser session or API key, anyone signed in |
| GET | [`/api/content/status`](#get-apicontentstatus) | How far the content queue has got | browser session or API key, anyone signed in |
| GET | [`/api/paper/content`](#get-apipapercontent) | What is known about a paper | browser session or API key, anyone signed in |
| POST | [`/api/papers/badges`](#post-apipapersbadges) | What is ready, for many papers | browser session or API key, anyone signed in |
| POST | [`/api/papers/retry`](#post-apipapersretry) | Try a failed stage again | browser session or API key, anyone signed in |

### GET /api/content/papers

The papers a stage has not finished

A stage's papers in some states, a page at a time: the ones still to do, or the failures with why, when they first and last failed, and how many tries -- the Status and Errors screens.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`content_papers`](mcp.md#content_papers) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `stage` | query | string | no | one of `openalex`, `methods`, `code`, `datasets`, `modalities`, `figures`, `ocr`; default `openalex` | The stage. |
| `state` | query | string | no | one of `unfinished`, `failed`, `not_found`, `errors`, `pending`, `done`; default `unfinished` | "unfinished" (default): pending, running and failed. "errors": failed and not found. |
| `q` | query | string | no |  | Only papers whose title, DOI or error contains this. |
| `sort` | query | string | no | one of `added`, `title`, `year`, `journal`, `state`, `error`, `attempts`, `first_failed`, `last_failed`; default `added` | Default added (newest first). |
| `dir` | query | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `limit` | query | integer | no | 1 to 1000; default `100` | Rows to return. Default 100. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `papers` | array of object | yes |  | key, title, doi, year, state, attempts, error, first_failed, last_failed, next_at. |
| `total` | integer | yes |  |  |

### GET /api/content/status

How far the content queue has got

Per stage, how many papers are done, pending, running, failed or not found; the missing pool's size; what is running.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`content_status`](mcp.md#content_status) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `library` | object | yes |  | papers, with_text, no_pdf, text_pending. |
| `openalex_enabled` | boolean | yes |  |  |
| `openalex_key` | boolean | yes |  | Whether library.openalex_api_key is set. |
| `pool` | map of integer | yes |  | The missing pool: all, refs, citing, and papers (library papers whose network is in). |
| `running` | map of string | yes |  | The paper each lane (net, local) is working on now. |
| `stages` | map of map of integer | yes |  | Per stage, how many papers are in each state. |
| `workers` | array of object | yes |  | The heavy-stage workers (`python -m app worker`) that checked in lately: id, host, pid, started, beat, doing (the task in hand), stages, alive (checked in within 90 s). |

### GET /api/paper/content

What is known about a paper

Everything derived about one paper so far: its sections (the methods split), code and dataset links, modality tags, its OpenAlex network, and the state of each stage. Asking moves its unfinished stages to the front of the queue, so what someone is looking at is done first.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_paper_content`](mcp.md#get_paper_content) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no |  | The paper's key, from search_library. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `content` | object | yes |  | stages: each stage's state (pending, running, done, failed, not_found, none) with its error and summary; sections (the text split on its headings), code, data and names (links and datasets found), modalities, network (OpenAlex id, reference and citer counts, how many of each are in the library) and openalex_abstract. |
| `key` | string | yes |  |  |
| `lists` | array of object | yes |  | The lists the paper is on: slug, name, position. |

### POST /api/papers/badges

What is ready, for many papers

A short summary of each paper's content, for the badges on every row that shows a paper.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`content_badges`](mcp.md#content_badges) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `keys` | array of string | yes |  | Paper keys. At most 5000. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `badges` | map of object | yes |  | Per key: states (each stage's state), code and data (how many links), methods (a methods section was found), mods, refs and citers, errors. |

### POST /api/papers/retry

Try a failed stage again

Put failed (and not-found) stages back in the queue at once: one paper's, one stage's across the library, or one paper's one stage. A not-found OpenAlex lookup is only ever asked again this way.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`retry_content`](mcp.md#retry_content) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `key` | string | no |  | A paper's key. Empty: every paper. |
| `stage` | string | no |  | One stage. Empty: every stage. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `queued` | integer | yes |  | How many stages were put back in the queue. |

## Crawl

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/crawl`](#get-apicrawl) | The crawl's progress and past runs | browser session or API key, anyone signed in |
| POST | [`/api/crawl`](#post-apicrawl) | Start a crawl | browser session or API key, anyone signed in |
| POST | [`/api/crawl/stop`](#post-apicrawlstop) | Stop the crawl | browser session or API key, anyone signed in |
| GET | [`/api/crawl/{search}`](#get-apicrawlsearch) | A saved search's last crawl | browser session or API key, anyone signed in |
| GET | [`/api/crawl/{search}/export.xlsx`](#get-apicrawlsearchexportxlsx) | A crawl as a workbook | browser session or API key, anyone signed in |

### GET /api/crawl

The crawl's progress and past runs

Whether a crawl is running and how far it has got, and the last crawl of each saved search.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`crawl_status`](mcp.md#crawl_status) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`CrawlStatus`](#crawlstatus).

### POST /api/crawl

Start a crawl

A best-first walk over OpenAlex from the library papers matching a saved search: score = keyword_weight x terms matched + cite_weight x log10(citations + 1) + link_weight x times reached. Runs in the background; GET /api/crawl says how far it has got, and the result replaces that search's last one.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`start_crawl`](mcp.md#start_crawl) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `api_budget` | integer | no | 0 to 20000; default `1000` | OpenAlex requests at most; 0 uses only what is cached. |
| `cite_weight` | number | no | 0 to 10; default `0.4` |  |
| `cited_by` | boolean | no | default `true` | Also walk forward, to the works citing each one. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `keyword_weight` | number | no | 0 to 10; default `1` |  |
| `link_weight` | number | no | 0 to 10; default `0.5` |  |
| `max_depth` | integer | no | 0 to 4; default `2` |  |
| `max_visits` | integer | no | 1 to 5000; default `500` |  |
| `min_novel_hits` | integer | no | 0 to 50; default `2` | Terms a work needs to be reported. |
| `min_seed_hits` | integer | no | 0 to 50; default `1` | Terms a library paper needs to be a seed. |
| `search` | string | yes | at least 1 characters | The saved search whose terms score the works (id or name). |

**Reply 202**: Success

[`CrawlStatus`](#crawlstatus).

### POST /api/crawl/stop

Stop the crawl

Stop the crawl under way; what it found so far is kept as its result.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`stop_crawl`](mcp.md#stop_crawl) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`CrawlStatus`](#crawlstatus).

### GET /api/crawl/{search}

A saved search's last crawl

The works the last crawl for a saved search found, best score first.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_crawl`](mcp.md#get_crawl) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |
| `view` | query | string | no | one of `novel`, `visited`; default `novel` | "novel" (default): works you lack. "visited": every work walked. |
| `limit` | query | integer | no | 1 to 2000; default `500` |  |

**Reply 200**: Success

[`CrawlResult`](#crawlresult).

### GET /api/crawl/{search}/export.xlsx

A crawl as a workbook

The last crawl for a saved search: Novel and Visited sheets, with score, terms matched, links, depth and where each was reached from.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download. |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |

**Reply 200**: Success

Text, as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## Figures

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/figures`](#get-apifigures) | Papers and their figures | browser session or API key, anyone signed in |
| GET | [`/api/figures/export`](#get-apifiguresexport) | A view's picks as a file | browser session or API key, anyone signed in |
| GET | [`/api/figures/image`](#get-apifiguresimage) | One figure's image | browser session or API key, anyone signed in |
| POST | [`/api/figures/pick`](#post-apifigurespick) | Pick or unpick figures | browser session or API key, anyone signed in |
| POST | [`/api/figures/replace`](#post-apifiguresreplace) | Replace a view's picks | browser session or API key, anyone signed in |
| POST | [`/api/figures/skip`](#post-apifiguresskip) | Skip or unskip papers | browser session or API key, anyone signed in |
| GET | [`/api/figures/state`](#get-apifiguresstate) | A view's picks and skipped papers | browser session or API key, anyone signed in |

### GET /api/figures

Papers and their figures

The papers whose figures have been cropped, with their figures, a page of papers at a time: every figure, or the method figures (captions matching config/method-images.txt). Each figure says whether it is picked in this view and in the other; chips, modality and keyword filters narrow the papers.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_figures`](mcp.md#list_figures) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `view` | query | string | no | one of `all`, `method`; default `all` | "all" (default): every figure. "method": the figures whose caption reads as a model design. |
| `sort` | query | string | no | one of `added`, `published`, `match`, `count`, `title`; default `added` | added (default: when it reached Zotero), published, match (best caption match), count (most figures), title. |
| `dir` | query | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `chip` | query | string | no | one of `all`, `lead`, `selected`, `skipped`, `other`; default `all` | all (default: every paper not skipped), lead (a structural term opens a caption), selected (a figure is picked), skipped, other (a figure is picked in the other view). |
| `mod` | query | string | no |  | Only papers tagged with this modality. |
| `term` | query | string | no |  | Only papers with a caption matching this keyword (method view). |
| `q` | query | string | no |  | Only papers whose title, DOI or a caption contains this. |
| `limit` | query | integer | no | 1 to 200; default `40` | Papers to return. Default 40. |
| `offset` | query | integer | no | at least 0 | Papers to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `counts` | map of integer | yes |  | Papers under each chip: all, lead, selected, skipped, other. |
| `figures` | integer | yes |  | How many figures the matching papers show. |
| `mods` | array of object | yes |  | The modalities of the papers shown, with counts. |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `papers` | array of object | yes |  | key, title, year, doi, added, date, skipped, mods, terms, lead, best, and figures: n, id (<key>#figure-N), page, caption, w, h, dup, picked, picked_other, match (score, terms, strong, lead, spans). |
| `picks` | integer | yes |  | Figures picked in this view. |
| `skips` | integer | yes |  | Papers skipped in this view. |
| `terms` | array of object | yes |  | The caption keywords matched, with counts (method view). |
| `total` | integer | yes |  |  |
| `workers` | boolean | yes |  | Whether a figures worker is running now. |

### GET /api/figures/export

A view's picks as a file

Every picked figure of a view, in pick order, with its paper, DOI and caption: a JSON or CSV file to download.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download; figure_picks gives the ids as data. |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `view` | query | string | no | one of `all`, `method`; default `all` | "all" (default): every figure. "method": the figures whose caption reads as a model design. |
| `format` | query | string | no | one of `json`, `csv`; default `json` | json (default) or csv. |

**Reply 200**: Success

Raw bytes, as `application/octet-stream`.

### GET /api/figures/image

One figure's image

A figure crop: a small copy for the grid (WebP), or the full crop (PNG). n=0 is the paper's montage.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: An image, for a browser to show. |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no |  | The paper's key. |
| `n` | query | integer | no | at least 0 | The figure's number; 0 is the paper's montage. |
| `size` | query | string | no | one of `thumb`, `full`; default `thumb` | thumb (default, 640 px wide) or full (the 400 DPI crop). |

**Reply 200**: Success

Text, as `image/webp`.

### POST /api/figures/pick

Pick or unpick figures

Pick figures in one view (a new pick goes last), or take picks back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`pick_figures`](mcp.md#pick_figures) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `ids` | array of string | yes |  | Figure ids, "<paper key>#figure-N". At most 1000. |
| `pick` | boolean | no | default `true` | true picks them (default), false unpicks them. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `selected` | array of string | yes |  | The picked figures' ids, in pick order. |
| `skipped` | array of string | yes |  | The skipped papers' keys. |

### POST /api/figures/replace

Replace a view's picks

Set a view's picks and skipped papers outright: Clear sends both empty, and its undo sends the old ones back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_figure_picks`](mcp.md#set_figure_picks) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `selected` | array of string | no |  | The picks to keep, in order. |
| `skipped` | array of string | no |  | The skipped papers to keep. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `selected` | array of string | yes |  | The picked figures' ids, in pick order. |
| `skipped` | array of string | yes |  | The skipped papers' keys. |

### POST /api/figures/skip

Skip or unskip papers

Hide papers you are done with from one view, or bring them back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`skip_figure_papers`](mcp.md#skip_figure_papers) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `keys` | array of string | yes |  | Paper keys. At most 1000. |
| `skip` | boolean | no | default `true` | true skips them (default), false brings them back. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `selected` | array of string | yes |  | The picked figures' ids, in pick order. |
| `skipped` | array of string | yes |  | The skipped papers' keys. |

### GET /api/figures/state

A view's picks and skipped papers

Every picked figure (in pick order) and every skipped paper of one view.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`figure_picks`](mcp.md#figure_picks) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `view` | query | string | no | one of `all`, `method`; default `all` | "all" (default): every figure. "method": the figures whose caption reads as a model design. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `selected` | array of string | yes |  | The picked figures' ids, in pick order. |
| `skipped` | array of string | yes |  | The skipped papers' keys. |

## Google Sheets

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/lists/{slug}/sheet`](#get-apilistsslugsheet) | A list's Google Sheet mirror | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/sheet`](#post-apilistsslugsheet) | Mirror a list to a Google Sheet | browser session or API key, anyone signed in |

### GET /api/lists/{slug}/sheet

A list's Google Sheet mirror

Whether the list is mirrored to a Google Sheet, how, and how the last push and read-back went.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_list_sheet`](mcp.md#get_list_sheet) |
| Errors | 400, 401, 404, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes | 1 to 200 characters | The list's slug. |

**Reply 200**: Success

[`SheetMirror`](#sheetmirror).

### POST /api/lists/{slug}/sheet

Mirror a list to a Google Sheet

Switch a list's Google Sheet mirror off, one-way or two-way; sync now; or overwrite the sheet with the list.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`set_list_sheet`](mcp.md#set_list_sheet) |
| Errors | 400, 401, 403, 404, 409, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes | 1 to 200 characters | The list's slug. |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `mode` | string or null | no | one of `off`, `one-way`, `two-way` | off; one-way (the list is pushed to its sheet after each change); two-way (also read back every poll_seconds). The first switch on makes the spreadsheet. |
| `overwrite` | boolean | no |  | Write the list over the sheet now, dropping anything typed there since the last read. |
| `sync_now` | boolean | no |  | Push (and read back, two-way) now. |

**Reply 200**: Success

[`SheetMirror`](#sheetmirror).

## Library

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/exists`](#post-apiexists) | Which of these papers are in the library | browser session or API key, anyone signed in |
| GET | [`/api/library/links`](#get-apilibrarylinks) | What a paper's links need | browser session or API key, anyone signed in |
| GET | [`/api/library/status`](#get-apilibrarystatus) | How the library is doing | browser session or API key, anyone signed in |
| GET | [`/api/library/stream`](#get-apilibrarystream) | When the library moves | browser session or API key, anyone signed in |
| GET | [`/api/paper`](#get-apipaper) | One paper | browser session or API key, anyone signed in |
| GET | [`/api/paper/pdf`](#get-apipaperpdf) | A paper's PDF | browser session or API key, anyone signed in |
| GET | [`/api/papers`](#get-apipapers) | Search the library | browser session or API key, anyone signed in |
| GET | [`/api/papers/recent`](#get-apipapersrecent) | Papers added lately | browser session or API key, anyone signed in |
| GET | [`/api/version`](#get-apiversion) | The library's version token | browser session or API key, anyone signed in |

### POST /api/exists

Which of these papers are in the library

The userscripts' question: which of these papers is in the library. A DOI settles it; a title is matched only without one. Called with an API key (Authorization: Bearer), so it needs no csrf_token; a browser session sends one like any other POST.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`papers_exist`](mcp.md#papers_exist) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `queries` | array of object | yes |  | The papers to look for: {"id", "title", "doi"} each. At most 5000. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `results` | array of object | yes |  | {"id", "exists", "title", "doi"} for each query, in order. |

### GET /api/library/links

What a paper's links need

What the page needs to build a paper's links.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Settings for drawing the page's links, not something an agent acts on. |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `proxy_url` | string | yes |  | library.proxy_url: the prefix a paper's publisher link goes through. Empty for none. |

### GET /api/library/status

How the library is doing

Whether the catalogue has read Zotero yet, how many papers it holds, how many have their text indexed, and any error.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`library_status`](mcp.md#library_status) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `error` | string | yes |  |  |
| `papers` | integer | yes |  |  |
| `ready` | boolean | yes |  |  |
| `rev` | integer | yes |  |  |
| `text_pending` | integer | yes |  |  |
| `with_text` | integer | yes |  |  |

### GET /api/library/stream

When the library moves

Server-sent events: "changed" when papers were added, changed or removed, "progress" while full text is being indexed. The page fetches what it shows again.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A live event stream for the page; library_version is the polling equivalent. |
| Errors | 401, 429, 503 |

**Reply 200**: Success

Text, as `text/event-stream`.

### GET /api/paper

One paper

One paper in full: everything the library knows of it.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_paper`](mcp.md#get_paper) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no |  | The paper's Zotero key, from search_library. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `paper` | object | yes |  |  |

### GET /api/paper/pdf

A paper's PDF

The paper's first PDF that is on disk, to open in the browser.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The file itself, for a browser to show. |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no |  | The paper's Zotero key, from search_library. |

**Reply 200**: Success

Text, as `application/pdf`.

### GET /api/papers

Search the library

Search the papers in the Zotero library, a page at a time. mode "text" (default) is boolean full-text search over title, authors, abstract and the PDF's text: words are ANDed, OR between alternatives, -word or NOT word excludes, "a phrase" is literal. mode "title" finds a half-remembered title, typos and all, or a pasted DOI.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`search_library`](mcp.md#search_library) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `q` | query | string | no |  | The search. Empty lists every paper. Read up to 500 characters. |
| `mode` | query | string | no | one of `text`, `title`; default `text` | "text" (default): boolean full-text search. "title": a half-remembered title, typos and all, or a DOI. |
| `sort` | query | string | no | one of `relevance`, `added`, `year`, `title`, `journal`, `authors`; default `relevance` | Default relevance. authors orders by the first author. |
| `dir` | query | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `has` | query | string | no |  | Only papers with: "code" (code links found), "data" (dataset links or names), "no_text" (no PDF text), "no_openalex" (OpenAlex has no record, or the lookup failed). Several, comma-separated, must all hold. |
| `limit` | query | integer | no | 1 to 1000; default `50` | Papers to return. Default 50. |
| `offset` | query | integer | no | at least 0 | Papers to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `fuzzy` | boolean | yes |  | Whether the matches are near ones, not exact. |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `papers` | array of object | yes |  | Each paper as the library has it, with score (its relevance, or null) and content (what is ready of it, as content_badges gives it; null before its first stage is queued). |
| `status` | object | yes |  |  |
| `status.error` | string | yes |  |  |
| `status.papers` | integer | yes |  |  |
| `status.ready` | boolean | yes |  |  |
| `status.rev` | integer | yes |  |  |
| `status.text_pending` | integer | yes |  |  |
| `status.with_text` | integer | yes |  |  |
| `total` | integer | yes |  |  |

### GET /api/papers/recent

Papers added lately

Papers added in Zotero in the last days, newest first, leaving out those already on the list not_on names: "what did I save this week that isn't on this list yet?". Read from the live catalogue, so a paper saved seconds ago is there.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`recent_papers`](mcp.md#recent_papers) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `days` | query | integer | no | 1 to 3650; default `7` | How far back. Default 7. |
| `not_on` | query | string | no |  | A list's slug: leave out the papers already on it. |
| `limit` | query | integer | no | 1 to 1000; default `50` | Papers to return. Default 50. |
| `offset` | query | integer | no | at least 0 | Papers to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `papers` | array of object | yes |  |  |
| `total` | integer | yes |  |  |

### GET /api/version

The library's version token

A token that changes whenever the library does, so a userscript can poll cheaply and re-ask only then.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`library_version`](mcp.md#library_version) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `papers` | integer | yes |  |  |
| `version` | string | yes |  | Changes whenever the library does. |

## Lists

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/cite`](#post-apicite) | Cite papers | browser session or API key, anyone signed in |
| GET | [`/api/cite/styles`](#get-apicitestyles) | The citation styles | browser session or API key, anyone signed in |
| GET | [`/api/lists`](#get-apilists) | List the lists | browser session or API key, anyone signed in |
| POST | [`/api/lists`](#post-apilists) | Make a new list | browser session or API key, anyone signed in |
| GET | [`/api/lists/deleted`](#get-apilistsdeleted) | Deleted lists | browser session or API key, anyone signed in |
| GET | [`/api/lists/schema`](#get-apilistsschema) | List ops reference | browser session or API key, anyone signed in |
| GET | [`/api/lists/stream`](#get-apilistsstream) | When a list changes | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}`](#get-apilistsslug) | Read a list | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/delete`](#post-apilistsslugdelete) | Delete a list | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}/export.csv`](#get-apilistsslugexportcsv) | A list as CSV | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/export.csv`](#post-apilistsslugexportcsv) | Some of a list as CSV | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}/history`](#get-apilistsslughistory) | A list's past versions | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}/history/{rev}`](#get-apilistsslughistoryrev) | One past version of a list | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/lock`](#post-apilistssluglock) | Make a list view-only, or editable | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/ops`](#post-apilistsslugops) | Change a list | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}/remaining`](#get-apilistsslugremaining) | Library papers not on a list | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/rename`](#post-apilistsslugrename) | Rename a list | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/restore`](#post-apilistsslugrestore) | Put a past version back | browser session or API key, anyone signed in |
| GET | [`/api/lists/{slug}/rows`](#get-apilistsslugrows) | A list as flat rows | browser session or API key, anyone signed in |
| POST | [`/api/lists/{slug}/undelete`](#post-apilistsslugundelete) | Put a deleted list back | browser session or API key, anyone signed in |
| POST | [`/api/refs/parse`](#post-apirefsparse) | Read a reference list | browser session or API key, anyone signed in |
| POST | [`/api/sheet/csv`](#post-apisheetcsv) | Read a Google Sheet | browser session or API key, anyone signed in |

### POST /api/cite

Cite papers

Each paper's in-text and full citation in a CSL style.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`cite_papers`](mcp.md#cite_papers) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `keys` | array of string | yes |  | The papers' keys. At most 5000. |
| `list` | string | no |  | A list's slug: papers not in the library are cited from their row on it. |
| `style` | string | no |  | A CSL style from GET /api/cite/styles. Default: the list's, else library.cite_style. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `cites` | object | yes |  | {key: {intext, full}}. |
| `style` | string | yes |  |  |

### GET /api/cite/styles

The citation styles

The CSL styles on this server, usable or not (with why), and the default.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`cite_styles`](mcp.md#cite_styles) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `default` | string | yes |  |  |
| `styles` | array of any | yes |  |  |

### GET /api/lists

List the lists

Every curated list, the main one first: slug, name, rev (its version number), how many papers it holds, and whether it is view-only.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_lists`](mcp.md#list_lists) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `limit` | query | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `lists` | array of object | yes |  |  |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |

### POST /api/lists

Make a new list

A new list: empty, a full copy of the list `from` names, or a copy of only the rows `keys` names.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: An agent edits lists; which lists exist is a person's decision. |
| Errors | 400, 401, 403, 404, 410, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `from` | string | no |  | Copy this list (its slug) instead of starting empty. |
| `keys` | array of string or null | no |  | With from: copy only these rows (keys), and only the tags they use. |
| `name` | string | yes |  | The new list's name. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |

### GET /api/lists/deleted

Deleted lists

The lists in the trash, most recently deleted first. Each can be put back for 30 days.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Which lists exist is a person's decision. |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `days` | integer | yes |  | How long a deleted list can be put back. |
| `lists` | array of object | yes |  |  |

### GET /api/lists/schema

List ops reference

Every op POST /api/lists/{slug}/ops takes, with its parameters, plus how rows and positions are named.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_schema`](mcp.md#list_schema) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `about` | string | yes |  |  |
| `auth` | string | yes |  |  |
| `endpoints` | map of string | yes |  |  |
| `examples` | any | no |  |  |
| `ops` | any | no |  |  |
| `position` | any | no |  |  |
| `responses` | any | no |  |  |
| `row_selector` | any | no |  |  |

### GET /api/lists/stream

When a list changes

Server-sent events: "list" {slug, rev, by} whenever any list changes.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A live event stream for the page; get_list's rev says the same when asked. |
| Errors | 401, 429, 503 |

**Reply 200**: Success

Text, as `text/event-stream`.

### GET /api/lists/{slug}

Read a list

One list in full (a slug it was renamed away from answers the list as it is now): its document (rows in order, each with key, title, year, tags and cells; columns; the tag vocabulary with colours), its rev, and what the library knows of each row.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_list`](mcp.md#get_list) |
| Errors | 400, 401, 404, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |

### POST /api/lists/{slug}/delete

Delete a list

Into the trash: off the picker and its link, its versions kept. It can be put back for 30 days. The main list cannot be deleted.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Which lists exist is a person's decision. |
| Errors | 400, 401, 403, 404, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |

### GET /api/lists/{slug}/export.csv

A list as CSV

The list as CSV in its order: #, DOI_or_Key, Cite, Title, Year, Tags, <columns>, MD_File.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download; list_rows gives the same rows as data. |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |
| `keys` | query | string | no |  | Only these rows: their keys, comma-separated. Leave out for every row. |

**Reply 200**: Success

Text, as `text/csv`.

### POST /api/lists/{slug}/export.csv

Some of a list as CSV

The list as CSV in its order: #, DOI_or_Key, Cite, Title, Year, Tags, <columns>, MD_File. The rows to export are in the body.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download; list_rows gives the same rows as data. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `keys` | array of string or null | no |  | Only these rows, by key: the page's filter can be thousands, too long for a URL. |

**Reply 200**: Success

Text, as `text/csv`.

### GET /api/lists/{slug}/history

A list's past versions

The kept versions of a list (the last 40), newest first: rev, when, by whom, row and shelf counts. Version N is the list as it stood before the change that made rev N+1.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_history`](mcp.md#list_history) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |
| `limit` | query | integer | no | 1 to 1000; default `200` | Versions to return. Default 200. |
| `offset` | query | integer | no | at least 0 | Versions to skip. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `total` | integer | yes |  |  |
| `versions` | array of object | yes |  |  |

### GET /api/lists/{slug}/history/{rev}

One past version of a list

One kept version of a list, with its whole document.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_version`](mcp.md#list_version) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |
| `rev` | path | integer | yes | at least 1 | The version's rev, from list_history. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `version` | object | yes |  |  |

### POST /api/lists/{slug}/lock

Make a list view-only, or editable

View-only for everyone: ops then answer 403 (dry runs still work). Not a change to its document, so its rev stays put.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Which lists may change is a person's decision. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `locked` | boolean | yes |  | true: view-only for everyone; ops then answer 403. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |
| `ok` | boolean | yes |  |  |

### POST /api/lists/{slug}/ops

Change a list

Run a batch of ops against a list, atomically: every op succeeds and the list is saved once, or nothing is saved and the answer names the op that failed. Rows are named by key, DOI or "#N" (position). Examples: {"op":"add","paper":"<key or DOI or title>","at":"top"}, {"op":"move","row":"#12","to":1}, {"op":"tag","rows":["#1","#2"],"add":["premier"]}, {"op":"set_cell","row":"#1","col":"Notes","value":"key paper","mode":"append"}. dry_run previews; if_rev refuses the batch when the list moved since you read it. Every change keeps the previous version, so a removal can be put back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_ops`](mcp.md#list_ops) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `dry_run` | boolean | no |  | Preview: run the ops and answer, but save nothing. |
| `if_rev` | integer or null | no |  | Refuse the batch when the list has moved past this rev since you read it. |
| `ops` | array of object | yes |  | The ops, in order: {op, ...} each. GET /api/lists/schema names them all. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changed` | boolean | yes |  |  |
| `list` | object or null | no |  | The list afterwards. Left out of the MCP tool's answer: get_list has it. |
| `mirrored` | array of object | no |  | The other lists the tag and cell edits were made on too: {slug, name, papers} (or skipped: "locked"); and {filled, from} when papers arriving here were given what other lists say about them. |
| `ok` | boolean | yes |  |  |
| `results` | array of any | yes |  |  |
| `rev` | integer | yes |  |  |

### GET /api/lists/{slug}/remaining

Library papers not on a list

Every library paper not on the list (or its shelf), newest added first: what import_remaining picks from, in the order its range counts.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_remaining`](mcp.md#list_remaining) |
| Errors | 400, 401, 404, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `papers` | array of object | yes |  | {key, title, doi, year, journal, mods}, newest added first. |
| `total` | integer | yes |  |  |

### POST /api/lists/{slug}/rename

Rename a list

A new name, and the slug it makes (the old slug still answers, for links sent before). The main list keeps its slug.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Which lists exist, and what they are called, is a person's decision. |
| Errors | 400, 401, 403, 404, 410, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `name` | string | yes |  | The new name. The slug follows it; the old one keeps working as a link. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |

### POST /api/lists/{slug}/restore

Put a past version back

Put a kept version back as a new version, so it can be undone too. Refused while the list is view-only.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Restoring is done from the page, by a person. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `rev` | integer | yes |  | The kept version to put back. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object or null | yes |  |  |
| `ok` | boolean | yes |  |  |
| `rev` | integer | yes |  |  |

### GET /api/lists/{slug}/rows

A list as flat rows

The list as flat rows, each with its position and its cells under their column labels, filtered like the page's filter and tag bar.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_rows`](mcp.md#list_rows) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |
| `q` | query | string | no |  | A text filter. Read up to 500 characters. |
| `tags` | query | string | no |  | Tags to filter by, comma-separated. |
| `match` | query | string | no | one of `any`, `all`, `none`; default `any` | How the tags combine. Default any. |
| `shelf` | query | string | no |  | 1 or true: the staging shelf instead of the list. |
| `limit` | query | integer | no | 1 to 500; default `500` | Rows to return. Default 500. |
| `offset` | query | integer | no | at least 0 | Rows to skip. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `columns` | array of object | yes |  |  |
| `list` | integer | yes |  | How many rows the list holds. |
| `offset` | integer | yes |  |  |
| `options` | object | yes |  |  |
| `rev` | integer | yes |  |  |
| `rows` | array of object | yes |  |  |
| `shelf` | integer | yes |  | How many rows are on its staging shelf. |
| `slug` | string | yes |  |  |
| `tags` | array of object | yes |  |  |
| `total` | integer | yes |  |  |

### POST /api/lists/{slug}/undelete

Put a deleted list back

Out of the trash, at the slug it had.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: Which lists exist is a person's decision. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `slug` | path | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list` | object | yes |  |  |

### POST /api/refs/parse

Read a reference list

A pasted or dropped reference list, read and matched to the library: a preview of what the stage op puts on the shelf.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`parse_refs`](mcp.md#parse_refs) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `file` | string | no |  | Or a .docx or .txt file, base64. At most 10 MB. |
| `text` | string | no |  | A pasted reference list. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `max` | integer | yes |  |  |
| `refs` | array of any | yes |  |  |
| `text` | string | yes |  | What was read, so a dropped file can go on to the stage op. |

### POST /api/sheet/csv

Read a Google Sheet

A public Google Sheet's rows, and the links behind its cells, for an import. The request always goes to docs.google.com's own export, built from the sheet ID alone, so nothing else can be fetched. At most 20 MB.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: It reads a sheet for the page's import dialog; list_ops imports rows. |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `url` | string | yes |  | A Google Sheets link, shared as Anyone with the link. Only its sheet ID (and gid) are used. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `links` | array of any or null | no |  | Per row: null, or {column index: [[text, url or null], ...]} for each cell with links behind its text. |
| `links_error` | string | no |  | Why the links could not be read, when they could not (the rows still came). |
| `rows` | array of array of string | yes |  | The sheet's tab as rows of cells, the header first. |

## Missing papers

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/missing`](#get-apimissing) | Search the papers you do not have | browser session or API key, anyone signed in |
| GET | [`/api/missing/authors`](#get-apimissingauthors) | Who you cite most and lack | browser session or API key, anyone signed in |
| POST | [`/api/missing/skip`](#post-apimissingskip) | Skip or unskip missing papers | browser session or API key, anyone signed in |

### GET /api/missing

Search the papers you do not have

The missing pool: works your library cites, and works citing it, that are not in the library, with how many of your papers connect to each. Searched with the library's grammar, sorted on several columns, a page at a time. It fills in as each paper's OpenAlex stage lands.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`search_missing`](mcp.md#search_missing) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `q` | query | string | no |  | The search, the library's boolean grammar. Read up to 500 characters. |
| `pool` | query | string | no | one of `all`, `refs`, `citing`; default `all` | "all" (default), "refs" (works your library cites), "citing" (works citing your library). |
| `sort` | query | string | no |  | Columns, most important first: "conn:desc,year:desc". Columns: relevance (only while searching), conn, cited_by, title, year. Default conn:desc. |
| `skipped` | query | string | no | one of `hide`, `show`; default `hide` | Default hide. |
| `paper` | query | string | no |  | Only this library paper's network: its references and citers that you lack. |
| `limit` | query | integer | no | 1 to 1000; default `100` | Rows to return. Default 100. |
| `offset` | query | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `counts` | map of integer | yes |  | all, refs, citing: the same search on each tab. |
| `next` | integer or null | yes |  | Offset of the next page, or null on the last one. |
| `paper` | object or null | no |  | The library paper a network filter names. |
| `skipped` | integer | yes |  | How many matching works are skipped. |
| `total` | integer | yes |  |  |
| `works` | array of object | yes |  | wid, doi, title, journal, year, cited_by (OpenAlex), oa_pdf, authors, lib_cites (library papers citing it), cites_lib (library papers it cites), conn (their sum), score, skipped. |

### GET /api/missing/authors

Who you cite most and lack

The top 100 authors of the works your library cites and does not have, by summed connections then paper count.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`missing_authors`](mcp.md#missing_authors) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `authors` | array of object | yes |  | openalex, name, orcid, papers (in the pool), lib_cites (summed connections). |

### POST /api/missing/skip

Skip or unskip missing papers

Hide works from the Missing screen (a soft hide, undone by skip false), or bring them back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`skip_missing`](mcp.md#skip_missing) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `skip` | boolean | no | default `true` | true hides them (default); false shows them again. |
| `wids` | array of string | yes |  | OpenAlex ids ("W123"). At most 1000. |

**Reply 200**: Success

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changed` | integer | yes |  |  |

## Missing pool

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/missing/export.xlsx`](#get-apimissingexportxlsx) | The missing pool as a workbook | browser session or API key, anyone signed in |

### GET /api/missing/export.xlsx

The missing pool as a workbook

The old missing.xlsx, from the live pool: the top works by connections, the newest, the most cited, the top authors, and one sheet per saved search. Each row has its DOI, proxy and open-access links, year, journal and connections. Skipped works are left out.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download. |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `top` | query | integer | no | 10 to 5000; default `1000` | Rows per sheet. Default 1000. |
| `searches` | query | boolean | no | default `true` | Also a sheet per saved search (default true). |

**Reply 200**: Success

Text, as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## Research log

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/research-log/check`](#post-apiresearch-logcheck) | Which papers in a research log you lack | browser session or API key, anyone signed in |

### POST /api/research-log/check

Which papers in a research log you lack

Reads a Markdown research log (# 03SEP2026 date headings, &nbsp;-separated blocks of a title line and its links), lifts each paper's DOI out of its links, and checks each the way /api/exists does: a DOI settles it, else the title. A DOI miss is retried by title and marked recovered.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`check_research_log`](mcp.md#check_research_log) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `list_only` | boolean | no |  | Only what the parser extracted, unchecked: for a log whose layout drifted. |
| `name` | string | no | at most 200 characters; default `research log` | The file's name, for the report. |
| `text` | string | yes | at most 8388608 characters | The log's Markdown. |

**Reply 200**: Success

[`ResearchLogCheck`](#researchlogcheck).

## Review

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/review/library`](#get-apireviewlibrary) | The review of your curated papers | browser session or API key, anyone signed in |
| GET | [`/api/review/missing`](#get-apireviewmissing) | The review of the papers you do not have | browser session or API key, anyone signed in |
| GET | [`/api/review/missing/work`](#get-apireviewmissingwork) | One missing work's abstract screen | browser session or API key, anyone signed in |
| GET | [`/api/review/paper`](#get-apireviewpaper) | One paper's review with its evidence | browser session or API key, anyone signed in |

### GET /api/review/library

The review of your curated papers

Every paper on a list or with a picked figure, screened against the three inclusion criteria (fMRI dominant, decodes, attention in the authors' own model), with the values the screener extracted. Papers are screened one at a time as the content queue reaches them; those not reached yet are waiting.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_review`](mcp.md#list_review) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`ReviewLibrary`](#reviewlibrary).

### GET /api/review/missing

The review of the papers you do not have

The Missing pool screened on title and abstract alone with the same criteria, thresholds sized for an abstract: the works screened in, the near misses (failing exactly one criterion), the excluded tallied by reason, and how well the abstract screen agrees with the full-text one on your own papers. The pool is screened in the background as it fills; progress says how far.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_review_missing`](mcp.md#list_review_missing) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`ReviewMissing`](#reviewmissing).

### GET /api/review/missing/work

One missing work's abstract screen

Screens one work of the Missing pool on its abstract: the verdict with its why, and every value the abstract states with its quote.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_review_missing_work`](mcp.md#get_review_missing_work) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `wid` | query | string | no | at most 20 characters | The work's OpenAlex id (W...). |

**Reply 200**: Success

[`ReviewMissingWork`](#reviewmissingwork).

### GET /api/review/paper

One paper's review with its evidence

One candidate paper's review in full: every extracted value with the sentence it came from, and the alternatives.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_review`](mcp.md#get_review) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no | at most 200 characters | The paper's key. |

**Reply 200**: Success

[`ReviewPaper`](#reviewpaper).

## Saved searches

| Method | Path | Summary | Who may call |
|---|---|---|---|
| GET | [`/api/searches`](#get-apisearches) | The saved searches | browser session or API key, anyone signed in |
| POST | [`/api/searches`](#post-apisearches) | Save a search | browser session or API key, anyone signed in |
| POST | [`/api/searches/restore`](#post-apisearchesrestore) | Put a deleted search back | browser session or API key, anyone signed in |
| POST | [`/api/searches/try`](#post-apisearchestry) | Try a search before saving it | browser session or API key, anyone signed in |
| POST | [`/api/searches/{search}`](#post-apisearchessearch) | Change a saved search | browser session or API key, anyone signed in |
| POST | [`/api/searches/{search}/delete`](#post-apisearchessearchdelete) | Delete a saved search | browser session or API key, anyone signed in |
| GET | [`/api/searches/{search}/export`](#get-apisearchessearchexport) | A saved search's matches as a file | browser session or API key, anyone signed in |
| GET | [`/api/searches/{search}/run`](#get-apisearchessearchrun) | Run a saved search | browser session or API key, anyone signed in |

### GET /api/searches

The saved searches

Every saved search: a name, a boolean query and named groups of terms. The crawl and missing.xlsx use them.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`list_saved_searches`](mcp.md#list_saved_searches) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`SavedSearches`](#savedsearches).

### POST /api/searches

Save a search

A new saved search. A search that does not hold together is a 400 listing each problem with where it is.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`create_saved_search`](mcp.md#create_saved_search) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `name` | string | yes | 1 to 120 characters | Its name, unique. |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |

**Reply 201**: Success

[`SavedSearch`](#savedsearch).

### POST /api/searches/restore

Put a deleted search back

Undo a delete: the search as it was, with its id.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The page's undo; an agent makes the search again with create_saved_search. |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `search` | object | yes |  | The search as delete_saved_search answered it. |

**Reply 200**: Success

[`SavedSearch`](#savedsearch).

### POST /api/searches/try

Try a search before saving it

Run a search as sent, without saving it: what the editor shows as you type.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`try_saved_search`](mcp.md#try_saved_search) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `limit` | integer | no | 1 to 2000; default `200` |  |
| `name` | string | no | at most 120 characters; default `Unsaved` |  |
| `pool` | string | no | one of `library`, `missing`, `both`; default `both` | "both" (default), "library" or "missing". |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |

**Reply 200**: Success

[`SavedSearchRun`](#savedsearchrun).

### POST /api/searches/{search}

Change a saved search

Replace a saved search's name, query, groups and description.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`update_saved_search`](mcp.md#update_saved_search) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `name` | string | yes | 1 to 120 characters | Its name, unique. |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |

**Reply 200**: Success

[`SavedSearch`](#savedsearch).

### POST /api/searches/{search}/delete

Delete a saved search

Delete a saved search. The answer is the search as it was, which POST /api/searches/restore puts back.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`delete_saved_search`](mcp.md#delete_saved_search) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`SavedSearch`](#savedsearch).

### GET /api/searches/{search}/export

A saved search's matches as a file

Every match, library and missing, as an .xlsx (a sheet each) or a Markdown list.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download. |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |
| `format` | query | string | no | one of `xlsx`, `md`; default `xlsx` | "xlsx" (default) or "md". |

**Reply 200**: Success

Text, as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### GET /api/searches/{search}/run

Run a saved search

The library papers and missing works a saved search matches, and how many each of its groups matches alone.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`run_saved_search`](mcp.md#run_saved_search) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `search` | path | string | yes | 1 to 120 characters | The search's id, or its name. |
| `pool` | query | string | no | one of `library`, `missing`, `both`; default `both` | "both" (default), "library" or "missing". |
| `limit` | query | integer | no | 1 to 2000; default `500` | Rows of each pool to return. Default 500, at most 2000. |

**Reply 200**: Success

[`SavedSearchRun`](#savedsearchrun).

## Screener

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/review/check`](#post-apireviewcheck) | Check screener rules without saving | browser session or API key, admins |
| GET | [`/api/review/guide`](#get-apireviewguide) | How screener rules are written | browser session or API key, admins |
| GET | [`/api/review/overrides`](#get-apireviewoverrides) | Hand-checked review values | browser session or API key, admins |
| POST | [`/api/review/overrides`](#post-apireviewoverrides) | Set a paper's hand-checked values | browser session or API key, admins |
| GET | [`/api/review/progress`](#get-apireviewprogress) | How far the screener has got | browser session or API key, admins |
| GET | [`/api/review/setups`](#get-apireviewsetups) | The screener's rule setups | browser session or API key, admins |
| POST | [`/api/review/setups`](#post-apireviewsetups) | Make a rule setup | browser session or API key, admins |
| GET | [`/api/review/setups/{setup}`](#get-apireviewsetupssetup) | One rule setup | browser session or API key, admins |
| POST | [`/api/review/setups/{setup}`](#post-apireviewsetupssetup) | Save a rule setup | browser session or API key, admins |
| POST | [`/api/review/setups/{setup}/activate`](#post-apireviewsetupssetupactivate) | Use a rule setup | browser session or API key, admins |
| POST | [`/api/review/setups/{setup}/delete`](#post-apireviewsetupssetupdelete) | Delete a rule setup | browser session or API key, admins |
| GET | [`/api/review/setups/{setup}/export`](#get-apireviewsetupssetupexport) | A rule setup as YAML | browser session or API key, admins |
| POST | [`/api/review/setups/{setup}/reset`](#post-apireviewsetupssetupreset) | Reset the default rule setup | browser session or API key, admins |
| POST | [`/api/review/test`](#post-apireviewtest) | Try the screener on one paper | browser session or API key, admins |

### POST /api/review/check

Check screener rules without saving

Whether rules load (every pattern compiles, every value has the right type): a whole document, a setup, or a setup with changes made. And how many papers using them would re-screen.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`check_screener_rules`](mcp.md#check_screener_rules) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `rules` | object or null | no |  | A whole rules document to check. |
| `setup` | string | no |  | A setup to check, or to make changes to first. |

**Reply 200**: Success

[`ReviewCheck`](#reviewcheck).

### GET /api/review/guide

How screener rules are written

What an agent needs to write a setup: how patterns, macros and templates work, the change-path syntax, and the document's schema.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`screener_rules_guide`](mcp.md#screener_rules_guide) |
| Errors | 401, 403, 429, 503 |

**Reply 200**: Success

[`ScreenerGuide`](#screenerguide).

### GET /api/review/overrides

Hand-checked review values

Values typed in by hand, by paper: each wins over what the screener extracted, whatever the setup, and flags the paper.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`list_review_overrides`](mcp.md#list_review_overrides) |
| Errors | 401, 403, 429, 503 |

**Reply 200**: Success

[`ReviewOverrides`](#reviewoverrides).

### POST /api/review/overrides

Set a paper's hand-checked values

Replaces one paper's overrides; sending no fields removes them. Nothing is re-screened: overrides apply when read.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`set_review_override`](mcp.md#set_review_override) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `fields` | map of string | yes |  | Field -> value. Empty values are dropped; none at all deletes the override. |
| `key` | string | yes | at least 1 characters | The paper's key (or its DOI). |

**Reply 200**: Success

[`ReviewOverrides`](#reviewoverrides).

### GET /api/review/progress

How far the screener has got

Candidates, and how many are screened under the setup in use, waiting, or failed.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`screener_progress`](mcp.md#screener_progress) |
| Errors | 401, 403, 429, 503 |

**Reply 200**: Success

[`ReviewProgress`](#reviewprogress).

### GET /api/review/setups

The screener's rule setups

Every named set of screener rules, and which one is in use.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`list_screener_setups`](mcp.md#list_screener_setups) |
| Errors | 401, 403, 429, 503 |

**Reply 200**: Success

[`ScreenerSetups`](#screenersetups).

### POST /api/review/setups

Make a rule setup

A new named setup: a copy of another (source), or a whole rules document (rules), with changes made to it. Rules that do not load are a 400 listing each problem with where it is; nothing is made. It is not used until activated.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`create_screener_setup`](mcp.md#create_screener_setup) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `activate` | boolean | no |  | Use it at once (re-screens the candidate papers). |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `description` | string | no | at most 2000 characters | What it is for. |
| `name` | string | yes | 1 to 80 characters | Its name, unique. |
| `rules` | object or null | no |  | A whole rules document to start from instead of a copy. |
| `source` | string | no | default `default` | The setup to copy (default "default"). Ignored when rules are sent. |

**Reply 201**: Success

[`ScreenerSetup`](#screenersetup).

### GET /api/review/setups/{setup}

One rule setup

A setup's whole rules -- every word list, threshold, extraction field and dataset -- with config/review.yaml's defaults beside them and the paths where they differ.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`get_screener_setup`](mcp.md#get_screener_setup) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Reply 200**: Success

[`ScreenerSetup`](#screenersetup).

### POST /api/review/setups/{setup}

Save a rule setup

Changes a setup's rules (whole, or by changes), name or description. A pattern that does not compile, or a missing or wrong-typed value, is a 400 listing each problem with where it is; nothing is saved. Saving the setup in use re-screens the candidate papers one at a time; saving another re-screens nothing.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`save_screener_setup`](mcp.md#save_screener_setup) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `base_signature` | string | no |  | The signature the setup had when read: if it has changed since, nothing is saved and the answer is a 409 with the current signature. |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `description` | string or null | no | at most 2000 characters | A new description (not for the default). |
| `name` | string or null | no | at most 80 characters | A new name (not for the default). |
| `rules` | object or null | no |  | The whole rules document. |

**Reply 200**: Success

[`ScreenerSetup`](#screenersetup).

### POST /api/review/setups/{setup}/activate

Use a rule setup

Screens with this setup from now on. Each candidate paper takes the result it already has for this setup's rules when its text has not changed, and is re-screened in the background otherwise.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`use_screener_setup`](mcp.md#use_screener_setup) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`ScreenerSetup`](#screenersetup).

### POST /api/review/setups/{setup}/delete

Delete a rule setup

Deletes a setup for good. The default, and the setup in use, cannot be deleted.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`delete_screener_setup`](mcp.md#delete_screener_setup) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`ScreenerSetups`](#screenersetups).

### GET /api/review/setups/{setup}/export

A rule setup as YAML

A setup's rules in config/review.yaml's shape: to keep, or to paste in as the new defaults.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | None, HTTP only: A file to download; get_screener_setup gives the same rules as JSON. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Reply 200**: Success

Text, as `application/yaml`.

### POST /api/review/setups/{setup}/reset

Reset the default rule setup

Drops the default setup's edits: config/review.yaml as it is. Only the default can be reset.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`reset_screener_setup`](mcp.md#reset_screener_setup) |
| Errors | 400, 401, 403, 404, 409, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `setup` | path | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`ScreenerSetup`](#screenersetup).

### POST /api/review/test

Try the screener on one paper

Screens one library paper (key) or pasted text with the rules sent (unsaved), a setup, or the setup in use -- with changes made first, if sent -- and returns the verdict, why, and every extracted field with its quote. Nothing is stored.

|  |  |
|---|---|
| Who may call | browser session or API key, admins |
| MCP tool | [`test_screener`](mcp.md#test_screener) |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `abstract` | string | no |  |  |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `key` | string | no |  | A paper to screen, by its key. |
| `mode` | string | no | one of `full`, `abstract`; default `full` |  |
| `rules` | object or null | no |  | Rules to test with, not saved. |
| `setup` | string | no |  | A setup to test with (when no rules are sent); none means the one in use. |
| `text` | string | no |  | Pasted text to screen as the paper's body (and methods). |
| `title` | string | no |  |  |

**Reply 200**: Success

[`ReviewTest`](#reviewtest).

## Summaries

| Method | Path | Summary | Who may call |
|---|---|---|---|
| POST | [`/api/summaries`](#post-apisummaries) | Summarise papers | browser session or API key, anyone signed in |
| POST | [`/api/summaries/cancel`](#post-apisummariescancel) | Empty the summaries queue | browser session or API key, anyone signed in |
| POST | [`/api/summaries/delete`](#post-apisummariesdelete) | Delete a summary | browser session or API key, anyone signed in |
| GET | [`/api/summaries/paper`](#get-apisummariespaper) | One paper's summaries | browser session or API key, anyone signed in |
| POST | [`/api/summaries/put`](#post-apisummariesput) | Put a summary back | browser session or API key, anyone signed in |
| GET | [`/api/summaries/rollup`](#get-apisummariesrollup) | One section's summaries as a table | browser session or API key, anyone signed in |
| GET | [`/api/summaries/rollup.xlsx`](#get-apisummariesrollupxlsx) | The rollup as a workbook | browser session or API key, anyone signed in |
| GET | [`/api/summaries/status`](#get-apisummariesstatus) | The summaries queue | browser session or API key, anyone signed in |

### POST /api/summaries

Summarise papers

Queue LLM summaries of these papers' sections. One call each, in the background, with config.yaml's llm: provider; each one costs money, so a section already summarised is skipped unless force. Progress arrives on the library stream as "summary" events.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`summarize_papers`](mcp.md#summarize_papers) |
| Errors | 400, 401, 403, 409, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `force` | boolean | no |  | Summarise again a section already summarised. |
| `keys` | array of string | yes |  | Paper keys, at most 2000. |
| `sections` | array of string | yes |  | Sections to summarise: all (the whole text), abstract, introduction, background, methods, results, conclusions or future. |

**Reply 202**: Success

[`SummariesQueued`](#summariesqueued).

### POST /api/summaries/cancel

Empty the summaries queue

Drop every queued summary; the one being written finishes.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`cancel_summaries`](mcp.md#cancel_summaries) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |

**Reply 200**: Success

[`SummariesQueued`](#summariesqueued).

### POST /api/summaries/delete

Delete a summary

Forget one paper's summary of one section.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`delete_summary`](mcp.md#delete_summary) |
| Errors | 400, 401, 403, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `key` | string | yes | at least 1 characters |  |
| `section` | string | yes | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future` |  |

**Reply 200**: Success

[`SummaryDeleted`](#summarydeleted).

### GET /api/summaries/paper

One paper's summaries

Every summary kept for a paper, and those queued or failed.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`get_paper_summaries`](mcp.md#get_paper_summaries) |
| Errors | 400, 401, 404, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `key` | query | string | no |  | The paper's key. |

**Reply 200**: Success

[`PaperSummaries`](#papersummaries).

### POST /api/summaries/put

Put a summary back

Undo a delete: the summary as it was.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: The page's undo; an agent asks for the summary again with summarize_papers. |
| Errors | 400, 401, 403, 404, 429, 503 |

**Request body**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `csrf_token` | string | no |  | From GET /api/me. Browser sessions only. |
| `key` | string | yes | at least 1 characters |  |
| `section` | string | yes | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future` |  |
| `summary` | object | yes |  | {hashtags, summary, provider, model, at, by}: what delete answered. |

**Reply 200**: Success

[`SummaryDeleted`](#summarydeleted).

### GET /api/summaries/rollup

One section's summaries as a table

Every summary of a section: their subsection headers as columns, the hashtags and a histogram of them, and the extra keyword / regex columns config/rollup-extra-columns.yaml declares.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`summaries_rollup`](mcp.md#summaries_rollup) |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `section` | query | string | no | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future`; default `methods` | The section to roll up: all (the whole text), abstract, introduction, background, methods, results, conclusions or future. |

**Reply 200**: Success

[`SummariesRollup`](#summariesrollup).

### GET /api/summaries/rollup.xlsx

The rollup as a workbook

The rollup's Summaries sheet (a column per subsection and extra column) and its Hashtag counts.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | None, HTTP only: A file to download. |
| Errors | 400, 401, 429, 503 |

**Parameters**

| Name | In | Type | Required | Limits | Description |
|---|---|---|---|---|---|
| `section` | query | string | no | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future`; default `methods` | The section to roll up: all (the whole text), abstract, introduction, background, methods, results, conclusions or future. |

**Reply 200**: Success

Text, as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### GET /api/summaries/status

The summaries queue

Which language model writes the summaries, what is queued, and how many are kept per section.

|  |  |
|---|---|
| Who may call | browser session or API key, anyone signed in |
| MCP tool | [`summaries_status`](mcp.md#summaries_status) |
| Errors | 401, 429, 503 |

**Reply 200**: Success

[`SummariesStatus`](#summariesstatus).

## Schemas

The shapes the routes above refer to by name.

### APIKey

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `created_at` | string (date-time) | yes |  |  |
| `created_by` | integer | no |  | The admin who made this key for its owner. Absent if the owner made it. |
| `created_by_name` | string | no |  |  |
| `display_name` | string | no |  | The key's owner. On the admin list only. |
| `expired` | boolean | yes |  |  |
| `expires_at` | string (date-time) | no |  |  |
| `id` | string | yes |  |  |
| `last_used_at` | string (date-time) | no |  |  |
| `live` | boolean | yes |  |  |
| `may_sign_in` | boolean | yes |  | Whether this key may make a login link for its own account. |
| `name` | string | yes |  |  |
| `revoked` | boolean | yes |  |  |
| `revoked_at` | string (date-time) | no |  |  |
| `role` | string | yes | one of `admin`, `user` |  |
| `user_id` | integer | yes |  |  |

### BulkReply

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `done` | integer | yes |  | How many items worked. |
| `failed` | integer | yes |  | How many did not. |
| `results` | array of [`BulkResult`](#bulkresult) | yes |  | One per item, in the order they were sent. |

### BulkResult

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `error` | string | no |  | When it failed: the route's words for why. |
| `index` | integer | yes |  | The item's place in items, from 0. |
| `ok` | boolean | yes |  |  |
| `reply` | object | no |  | When it worked: the route's own reply, if it has one. |
| `request_id` | string | no |  | On a 5xx: the reference that finds this failure in the log. |
| `status` | integer | no |  | When it failed: the status the route would have answered. |

### CrawlResult

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `run` | object or null | yes |  | The run's settings and counts, null when it never ran. |
| `total` | integer | yes |  |  |
| `works` | array of object | yes |  | wid, doi, title, journal, year, cited_by, oa_pdf, authors, score, hits (terms matched), links (times reached), depth, from / from_title / from_key (the work it was reached from, and its library key when a seed), how (cites / cited by), in_library (it has been added since). |

### CrawlStatus

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `defaults` | object | yes |  | The crawl's default settings. |
| `runs` | array of object | yes |  | Each saved search's last crawl: settings, terms, seeds, visited, novel, api_used, errors, when. |
| `status` | object | yes |  | running, search_id, search, visited, novel, api_used, max_visits, started_at / finished_at, error. |

### Error

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `error` | string | yes |  |  |
| `request_id` | string | no |  | On a 5xx: the reference that finds this failure in the log. |

### IPNames

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `names` | array of object | yes |  |  |
| `names[].created_at` | string (date-time) | yes |  |  |
| `names[].name` | string | yes |  |  |
| `names[].target` | string | yes |  |  |

### Job

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `interrupted` | boolean | yes |  |  |
| `interval_seconds` | integer | yes |  |  |
| `last_error` | string | no |  |  |
| `last_finished` | string (date-time) | no |  |  |
| `last_note` | string | no |  |  |
| `last_ok` | boolean or null | no |  |  |
| `last_started` | string (date-time) | no |  |  |
| `name` | string | yes |  |  |
| `next_due` | string (date-time) | yes |  |  |
| `running` | boolean | yes |  |  |
| `runs` | integer | yes |  |  |

### LogDay

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `date` | string | yes |  |  |
| `entries` | array of object | yes |  |  |
| `next` | integer or null | yes |  |  |

### LogDays

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `days` | array of object | yes |  |  |
| `dropped` | integer | yes |  |  |
| `settings` | object | yes |  |  |
| `total_bytes` | integer | yes |  |  |

### LoginLink

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `created_at` | string (date-time) | yes |  |  |
| `expires_at` | string (date-time) or null | yes |  | null when it never expires. |
| `last_used_at` | string (date-time) or null | yes |  |  |
| `max_uses` | integer | yes |  | Sign-ins it allows. 0 when unlimited. |
| `unlimited` | boolean | yes |  |  |
| `uses` | integer | yes |  | Sign-ins so far. |

### Maintenance

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `error` | string | yes |  |  |
| `maintenance` | string | yes | one of `read_only`, `full` |  |

### Me

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `account_role` | string | yes |  |  |
| `announcement` | string | yes |  | server.announcement. Empty when there is none. |
| `api_key_id` | string | no |  | API keys only. |
| `api_key_name` | string | no |  | API keys only. |
| `api_keys_enabled` | boolean | yes |  |  |
| `auth` | string | yes |  |  |
| `authenticated` | boolean | yes |  |  |
| `csrf_token` | string | no |  | Browser sessions only. |
| `description` | string | yes |  | app.description. Empty when there is none. |
| `display_name` | string | yes |  |  |
| `id` | integer | yes |  |  |
| `is_owner` | boolean | yes |  |  |
| `login_link` | [`LoginLink`](#loginlink) or null | yes |  | Your own live login link, or null. |
| `logs_enabled` | boolean | yes |  |  |
| `logs_ui_clicks` | boolean | yes |  |  |
| `maintenance` | string | yes | one of `none`, `read_only`, `full` |  |
| `mcp_enabled` | boolean | yes |  | server.mcp: whether POST /mcp answers. |
| `mcp_url` | string | yes |  | Where to read the MCP reference: config/mcp.json in app.repo, or /api/mcp.json when there is no repo. Only with server.mcp on. |
| `openapi_url` | string | yes |  | Where to read this API's reference: config/api.json in app.repo, or /api/api.json when there is no repo. |
| `repo` | string | yes |  | app.repo without a trailing / or .git: where the source lives. Empty when it is not set. |
| `role` | string | yes |  | The effective role: never higher than an API key's own. |
| `shortcuts` | map of string | yes |  | The keyboard shortcuts you changed, by action. Mod is Cmd on a Mac and Ctrl elsewhere. |
| `show_about` | boolean | yes |  | app.show_about: whether the menu has About. |
| `tag_colors` | string | yes |  | Where your tag colours come from: wsu or theme (see POST /api/account/tag-colors). |
| `theme_id` | string | yes |  | The theme you use. Empty: the first. |
| `themes` | array of [`Theme`](#theme) or null | yes |  | Your themes (see the Theme schema): your own list, else the app's defaults, else null for the built-in ones. |
| `themes_builtins` | integer | yes |  | Which built-in themes that list has seen (see builtins on POST /api/account/themes). |
| `themes_custom` | boolean | yes |  | Whether you have your own list rather than following the defaults. |
| `two_factor` | boolean | yes |  |  |
| `two_factor_enabled` | boolean | yes |  |  |
| `version` | string | yes |  | The running build. dev when none was stamped. |

### Member

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes |  |  |
| `id` | integer | yes |  |  |

### NewAPIKey

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `created_at` | string (date-time) | yes |  |  |
| `created_by` | integer | no |  | The admin who made this key for its owner. Absent if the owner made it. |
| `created_by_name` | string | no |  |  |
| `credential` | string | yes |  | Shown in this response only, and never recoverable. |
| `display_name` | string | no |  | The key's owner. On the admin list only. |
| `expired` | boolean | yes |  |  |
| `expires_at` | string (date-time) | no |  |  |
| `id` | string | yes |  |  |
| `last_used_at` | string (date-time) | no |  |  |
| `live` | boolean | yes |  |  |
| `may_sign_in` | boolean | yes |  | Whether this key may make a login link for its own account. |
| `name` | string | yes |  |  |
| `revoked` | boolean | yes |  |  |
| `revoked_at` | string (date-time) | no |  |  |
| `role` | string | yes | one of `admin`, `user` |  |
| `user_id` | integer | yes |  |  |

### PaperSummaries

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `summaries` | map of object | yes |  | By section: hashtags, summary (Markdown), provider, model, at, by, cut (the text was too long and was cut), and state (done, queued, running, failed) with error. |

### PruneResult

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `bytes_after` | integer | yes |  |  |
| `bytes_before` | integer | yes |  |  |
| `compressed` | integer | yes |  |  |
| `deleted` | integer | yes |  |  |

### ResearchLogCheck

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `extracted` | integer | yes |  | Paper blocks found. |
| `lines` | integer | yes |  |  |
| `missing` | integer | no |  |  |
| `papers` | array of object | yes |  | Each paper: title, line, date (the heading above it), url, doi, occurrences (lines), mentions, and when checked: found ("doi", "title" or "" for missing), recovered (its DOI is not in the library but its title is), key. |
| `recovered` | integer | no |  |  |
| `report` | string | no |  | The Markdown report, as the old command wrote it. |
| `source` | string | yes |  |  |
| `unique` | integer | yes |  | After merging repeats by title. |

### ReviewCheck

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `problems` | array of map of string | yes |  | Each problem: path (where it is) and message. Empty: the rules load. |
| `rescreen` | integer | yes |  | Papers using these rules would re-screen (or take a kept result for). |
| `signature` | string | yes |  | The rules' signature; the same as the one in use means using them changes nothing. |

### ReviewLibrary

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `consensus` | array of object | yes |  | The dataset consensus: dataset, parameter, value, n, others, sources. |
| `counts` | map of integer | yes |  | included, borderline, excluded, waiting, failed, stale (screened under other rules). |
| `criteria` | array of string | yes |  |  |
| `criteria_abstract` | array of string | yes |  |  |
| `fields` | array of map of string | yes |  | The extraction fields in order: name, group. |
| `papers` | array of object | yes |  | Every candidate paper (on a list or with a picked figure): key, title, year, doi, journal, added, pubdate, cites, lists, tiers, figs, code_n, and state (included, borderline, excluded, waiting, failed). A screened paper adds current (screened under the rules in use), reason_code, reason, task, priority, attention_role, model_name, curated, datasets, notes; an excluded paper why (the tests it failed: test, detail), any other fields: {name: {value, source (auto, curated, dataset), alts, from_dataset, dataset_papers, note}} with only the fields the paper states. A field left out means the paper does not say. get_review gives one paper's quotes. |
| `problem` | string | yes |  |  |
| `reasons` | map of string | yes |  |  |
| `setup` | string | yes |  |  |
| `signature` | string | yes |  |  |
| `tasks` | array of object | yes |  |  |
| `unclassified_priority` | integer | yes |  |  |

### ReviewMissing

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `calibration` | object | yes |  | The abstract screen measured against the library's full-text verdicts: recall (found of total included), precision (agreed of passed), measured_over, configured_precision (shown while nothing can be measured), caveat. |
| `counts` | map of integer | yes |  | included, near_misses, excluded (near misses among them), no_abstract. |
| `criteria` | array of string | yes |  |  |
| `filling` | map of integer | yes |  | filled of papers: library papers whose OpenAlex network (and so their works' abstracts) is in the pool so far. Below papers, works are still arriving and many read as having no abstract. |
| `near_misses` | array of object | yes |  | Works failing exactly one criterion: the same, with near_miss and miss_label. |
| `papers` | array of object | yes |  | The works screened in, nearest your library first (at most 4000): wid, doi, title, journal, year, pubdate, cited_by, oa_pdf, authors, n_authors, lib_cites (your papers citing it), cites_lib (your papers it cites), conn, task, priority, model_name, datasets, attention_role. |
| `papers_cut` | integer | yes |  | Included works past the cap, not sent. |
| `progress` | map of integer | yes |  | screened (under the rules in use) of total works in the pool. |
| `reasons` | map of integer | yes |  | The excluded, tallied by reason code. |
| `signature` | string | yes |  |  |
| `skipped` | integer | yes |  |  |

### ReviewMissingWork

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `review` | object | yes |  | As get_review, from the abstract alone, with the abstract. |
| `wid` | string | yes |  |  |

### ReviewOverrides

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `overrides` | map of map of string | yes |  | Paper key (or DOI) -> {field: value}. |

### ReviewPaper

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | yes |  |  |
| `review` | object | yes |  | verdict (include, borderline, reason, task_category, priority, attention_role, why, task_evidence, attention_evidence), fields: {name: {group, value, values (most-stated first), counts, evidence (the sentences each value came from), source}}, datasets, model_name, curated, override, current. |

### ReviewProgress

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `in_use` | string | yes |  |  |
| `progress` | object | yes |  |  |
| `signature` | string | yes |  |  |

### ReviewTest

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `elapsed_ms` | integer | yes |  |  |
| `paper` | object | yes |  |  |
| `result` | object | yes |  | The review as the screens would show it: verdict with its why, fields with quotes. |
| `saved` | object or null | yes |  | The same paper under the setup in use, when testing other rules on a paper. |

### Revoked

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `api_keys` | integer | yes |  |  |
| `login_links` | integer | yes |  |  |
| `sessions` | integer | yes |  |  |

### SavedSearch

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `search` | object | yes |  |  |

### SavedSearchRun

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `library` | array of object | yes |  | Library papers matched, newest first: key, title, doi, year, journal, authors, added, tags. |
| `library_groups` | map of integer | yes |  | How many library papers each group matches on its own. |
| `library_total` | integer | yes |  |  |
| `missing` | array of object | yes |  | Missing works matched, by connections: wid, doi, title, journal, year, cited_by, oa_pdf, authors, conn. |
| `missing_groups` | map of integer | yes |  |  |
| `missing_total` | integer | yes |  |  |
| `search` | object | yes |  |  |

### SavedSearches

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `searches` | array of object | yes |  | Each search: id, name, description, query, groups, created / updated at and by. |

### ScreenerGuide

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `about` | string | yes |  | How the rules work: patterns, macros, templates. |
| `change_paths` | string | yes |  | The path syntax changes use. |
| `groups` | array of string | yes |  |  |
| `params` | array of string | yes |  |  |
| `post_kinds` | array of string | yes |  |  |
| `schema` | object | yes |  | The rules document's JSON schema. |
| `vocab_names` | array of string | yes |  |  |

### ScreenerSetup

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changed` | array of string | yes |  | Paths where the setup differs from the defaults, in the change-path syntax. |
| `defaults` | object | yes |  | config/review.yaml as shipped. |
| `edited` | boolean | yes |  |  |
| `groups` | array of string | yes |  |  |
| `in_use` | string | yes |  | The id of the setup in use. |
| `in_use_signature` | string | yes |  |  |
| `params` | array of string | yes |  |  |
| `post_kinds` | array of string | yes |  |  |
| `problem` | string | yes |  |  |
| `progress` | object | yes |  | Of the setup in use: candidates (papers on a list or with a picked figure), and of their review tasks: done, current (screened under the rules in use), waiting, failed, included, borderline. |
| `rules` | object | yes |  | The setup's rules (config/review.yaml's shape). |
| `setup` | object | yes |  | The setup's id, name, description and state, as in list_screener_setups. |
| `signature` | string | yes |  | The setup's signature: send it back as base_signature when saving. |
| `updated_at` | number or null | yes |  |  |
| `updated_by` | string | yes |  |  |
| `vocab_names` | array of string | yes |  |  |

### ScreenerSetups

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `in_use` | string | yes |  | The id of the setup in use. |
| `setups` | array of object | yes |  | Each setup, the default first: id, name, description, active (in use), builtin (the default), edited, signature, changed_count (places differing from config/review.yaml), based_on, updated_at, updated_by, problem (why it does not load). |

### Session

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `created_at` | string (date-time) | yes |  |  |
| `current` | boolean | yes |  |  |
| `expires_at` | string (date-time) | yes |  |  |
| `id` | string | yes |  |  |
| `ip` | string | no |  |  |
| `ip_name` | string | no |  | What the owner calls this address on the Logs screen. The owner's own list only. |
| `label` | string | no |  | The name you gave this device. |
| `last_seen_at` | string (date-time) | no |  |  |
| `user_agent` | string | no |  |  |

### SettingsResult

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `applied` | array of string or null | yes |  |  |
| `changes` | array of object or null | yes |  |  |
| `restart` | array of string or null | yes |  |  |
| `scripts` | array of string or null | yes |  |  |
| `unchanged` | array of string or null | yes |  |  |
| `version` | string | yes |  |  |

### SettingsSnapshot

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `error` | object or null | yes |  |  |
| `error.at` | string (date-time) | yes |  |  |
| `error.message` | string | yes |  |  |
| `error.origin` | string | yes |  |  |
| `file` | string | yes |  |  |
| `in_container` | boolean | yes |  |  |
| `secret_file` | string | yes |  |  |
| `sections` | array of object | yes |  |  |
| `sections[].help` | string | yes |  |  |
| `sections[].keys` | array of object | yes |  |  |
| `sections[].keys[].apply` | string | yes |  |  |
| `sections[].keys[].default` | any | yes |  |  |
| `sections[].keys[].file_only` | boolean | yes |  | A path: change it in config.yaml, never here. |
| `sections[].keys[].help` | string | yes |  |  |
| `sections[].keys[].in_file` | boolean | yes |  |  |
| `sections[].keys[].key` | string | yes |  |  |
| `sections[].keys[].locked` | boolean | yes |  |  |
| `sections[].keys[].name` | string | yes |  |  |
| `sections[].keys[].pending_restart` | boolean | yes |  |  |
| `sections[].keys[].running` | any | yes |  |  |
| `sections[].keys[].type` | string | yes |  |  |
| `sections[].keys[].value` | any | yes |  |  |
| `sections[].name` | string | yes |  |  |
| `stale` | boolean | yes |  |  |
| `version` | string | yes |  | Send it back when saving: a changed file is refused with a 409. |
| `writable` | boolean | yes |  |  |

### SheetMirror

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `sheet` | object | yes |  | available (google_sheets is on and has credentials), mode (off, one-way, two-way), spreadsheet_id, url, last_push, last_pull, error, refused (the last read-back was refused), note, pending, poll_seconds, default_mode. |

### SignIn

One of these:

1. An object:

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ok` | boolean | yes |  |  |

2. An object:

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `challenge` | string | yes |  |  |
| `two_factor` | boolean | yes |  |  |

### SummariesQueued

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `kept` | integer | yes |  | Already summarised, left alone (send force to redo). |
| `queued` | integer | yes |  |  |
| `unknown` | integer | yes |  | Keys that are not library papers. |

### SummariesRollup

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `columns` | array of string | yes |  | The "**Subsection.**" headers the summaries carry, in first-seen order. |
| `extra` | array of string | yes |  | The extra columns from config/rollup-extra-columns.yaml. |
| `hashtags` | array of array of any | yes |  | [hashtag, papers] most used first. |
| `rows` | array of object | yes |  | One per paper: key, title, doi, year, journal, hashtags, parts {header: text} (the whole summary, in its parts), extra {name: snippets}, model, at. |
| `section` | string | yes |  |  |

### SummariesStatus

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `counts` | map of integer | yes |  | Summaries kept, by section. |
| `done` | integer | yes |  | Summaries made since the server started. |
| `failed` | integer | yes |  |  |
| `model` | string | yes |  |  |
| `provider` | string | yes |  | The provider config.yaml picks: claude, openai or gemini; "" when no key is set. |
| `queued` | integer | yes |  |  |
| `running` | array of string or null | yes |  | [paper key, section] being summarised now. |
| `sections` | array of array of string | yes |  | [key, display name] of each section. |

### SummaryDeleted

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `summary` | object or null | yes |  | The summary as it was, for undo (POST /api/summaries/put). |

### Theme

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `accent` | string | yes |  | The main color: what you can press. |
| `background` | string | no |  | The page. Left out: the mode's own. |
| `button` | object or null | no |  | How the theme's buttons look. A choice left out is the default (rounded, normal, raised, normal). |
| `button.case` | string | no | one of `normal`, `upper` |  |
| `button.depth` | string | no | one of `flat`, `raised`, `glossy` |  |
| `button.shape` | string | no | one of `square`, `soft`, `rounded`, `pill` |  |
| `button.weight` | string | no | one of `normal`, `medium`, `bold` |  |
| `dark` | object or null | no |  | A light theme's colors for dark mode, kept while it is light. Switching the theme to dark swaps them in. A light theme's light (or a dark theme's dark) is dropped. |
| `dark.accent` | string | yes |  | The main color: what you can press. |
| `dark.background` | string | no |  | The page. Left out: the mode's own. |
| `dark.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `dark.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `dark.surface` | string | no |  | Cards. Left out: the mode's own. |
| `id` | string | yes |  | Lower-case letters, digits, - and _, up to 32. |
| `light` | object or null | no |  | A dark theme's colors for light mode, kept while it is dark. Switching the theme to light swaps them in. |
| `light.accent` | string | yes |  | The main color: what you can press. |
| `light.background` | string | no |  | The page. Left out: the mode's own. |
| `light.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `light.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `light.surface` | string | no |  | Cards. Left out: the mode's own. |
| `mode` | string | yes | one of `light`, `dark` |  |
| `name` | string | yes |  | 1 to 60 characters. |
| `overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `surface` | string | no |  | Cards. Left out: the mode's own. |

### User

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `created_at` | string (date-time) | yes |  |  |
| `disabled` | boolean | yes |  |  |
| `display_name` | string | yes |  |  |
| `id` | integer | yes |  |  |
| `login_link` | [`LoginLink`](#loginlink) or null | yes |  | The account's live login link, or null. |
| `owner` | boolean | yes |  |  |
| `role` | string | yes | one of `admin`, `user` |  |
| `two_factor` | boolean | yes |  |  |
