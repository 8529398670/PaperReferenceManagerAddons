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
- [Content](#content)
- [Library](#library)
- [Lists](#lists)
- [Missing papers](#missing-papers)
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
| `stage` | query | string | no | one of `openalex`, `methods`, `code`, `datasets`, `modalities`; default `openalex` | The stage. |
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

### PruneResult

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `bytes_after` | integer | yes |  |  |
| `bytes_before` | integer | yes |  |  |
| `compressed` | integer | yes |  |  |
| `deleted` | integer | yes |  |  |

### Revoked

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `api_keys` | integer | yes |  |  |
| `login_links` | integer | yes |  |  |
| `sessions` | integer | yes |  |  |

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
