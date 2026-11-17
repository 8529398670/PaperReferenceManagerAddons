# Paper Reference Manager MCP tools

This file is generated: do not edit it. Change the tools next to their handlers and run `scripts/api_docs.sh`. Every route is in [api.md](api.md).

Every tool POST /mcp offers. Written by scripts/api_docs.sh from the registered tools; do not edit by hand. A key sees the tools its role allows (adminOnly ones need an admin key), and a tool whose feature is switched off answers like one that does not exist. route is the HTTP route the tool stands for, with the same rules; http_only are the routes a key may call that have no tool, and why.

|  |  |
|---|---|
| Endpoint | `POST /mcp` |
| Transport | Streamable HTTP, stateless: one JSON-RPC message per POST, a JSON reply |
| Auth | Authorization: Bearer <API key> |

| Tool | Route | Who | What |
|---|---|---|---|
| [`admin_cancel_login_link`](#admin_cancel_login_link) | [`POST /api/admin/users/{user_id}/cancel-login-link`](api.md#post-apiadminusersuser_idcancel-login-link) | admin keys | Stop an account's login link working (admin) |
| [`admin_cancel_login_link_bulk`](#admin_cancel_login_link_bulk) | [`POST /api/bulk/admin/users/cancel-login-link`](api.md#post-apibulkadminuserscancel-login-link) | admin keys | Stop an account's login link working, for many at once (admin) |
| [`admin_create_user`](#admin_create_user) | [`POST /api/admin/users`](api.md#post-apiadminusers) | admin keys | Create an account (admin) |
| [`admin_delete_user`](#admin_delete_user) | [`POST /api/admin/users/{user_id}/delete`](api.md#post-apiadminusersuser_iddelete) | admin keys | Delete an account (admin) |
| [`admin_delete_user_bulk`](#admin_delete_user_bulk) | [`POST /api/bulk/admin/users/delete`](api.md#post-apibulkadminusersdelete) | admin keys | Delete an account, for many at once (admin) |
| [`admin_get_theme_defaults`](#admin_get_theme_defaults) | [`GET /api/admin/theme-defaults`](api.md#get-apiadmintheme-defaults) | admin keys | Default themes (admin) |
| [`admin_list_user_sessions`](#admin_list_user_sessions) | [`GET /api/admin/users/{user_id}/sessions`](api.md#get-apiadminusersuser_idsessions) | admin keys | An account's signed-in devices (admin) |
| [`admin_list_users`](#admin_list_users) | [`GET /api/admin/users`](api.md#get-apiadminusers) | admin keys | List users (admin) |
| [`admin_reissue_login`](#admin_reissue_login) | [`POST /api/admin/users/{user_id}/reissue-login`](api.md#post-apiadminusersuser_idreissue-login) | admin keys | A new login link for an account (admin) |
| [`admin_rename_user`](#admin_rename_user) | [`POST /api/admin/users/{user_id}/rename`](api.md#post-apiadminusersuser_idrename) | admin keys | Rename someone (admin) |
| [`admin_reset_two_factor`](#admin_reset_two_factor) | [`POST /api/admin/users/{user_id}/reset-two-factor`](api.md#post-apiadminusersuser_idreset-two-factor) | admin keys | Turn off an account's two-factor (admin) |
| [`admin_reset_two_factor_bulk`](#admin_reset_two_factor_bulk) | [`POST /api/bulk/admin/users/reset-two-factor`](api.md#post-apibulkadminusersreset-two-factor) | admin keys | Turn off an account's two-factor, for many at once (admin) |
| [`admin_revoke_access`](#admin_revoke_access) | [`POST /api/admin/users/{user_id}/revoke-access`](api.md#post-apiadminusersuser_idrevoke-access) | admin keys | Revoke a user's access (admin) |
| [`admin_revoke_access_bulk`](#admin_revoke_access_bulk) | [`POST /api/bulk/admin/users/revoke-access`](api.md#post-apibulkadminusersrevoke-access) | admin keys | Revoke a user's access, for many at once (admin) |
| [`admin_revoke_user_session`](#admin_revoke_user_session) | [`POST /api/admin/users/{user_id}/sessions/{session_id}/revoke`](api.md#post-apiadminusersuser_idsessionssession_idrevoke) | admin keys | Sign out one of an account's devices (admin) |
| [`admin_revoke_user_session_bulk`](#admin_revoke_user_session_bulk) | [`POST /api/bulk/admin/users/sessions/revoke`](api.md#post-apibulkadminuserssessionsrevoke) | admin keys | Sign out one of an account's devices, for many at once (admin) |
| [`admin_set_theme_defaults`](#admin_set_theme_defaults) | [`POST /api/admin/theme-defaults`](api.md#post-apiadmintheme-defaults) | admin keys | Replace the default themes (admin) |
| [`admin_set_user_disabled`](#admin_set_user_disabled) | [`POST /api/admin/users/{user_id}/disabled`](api.md#post-apiadminusersuser_iddisabled) | admin keys | Disable or enable a user (admin) |
| [`admin_set_user_disabled_bulk`](#admin_set_user_disabled_bulk) | [`POST /api/bulk/admin/users/disabled`](api.md#post-apibulkadminusersdisabled) | admin keys | Disable or enable a user, for many at once (admin) |
| [`admin_set_user_role`](#admin_set_user_role) | [`POST /api/admin/users/{user_id}/role`](api.md#post-apiadminusersuser_idrole) | admin keys | Change an account's role (admin) |
| [`admin_set_user_role_bulk`](#admin_set_user_role_bulk) | [`POST /api/bulk/admin/users/role`](api.md#post-apibulkadminusersrole) | admin keys | Change an account's role, for many at once (admin) |
| [`cancel_my_login_link`](#cancel_my_login_link) | [`POST /api/account/login-link/cancel`](api.md#post-apiaccountlogin-linkcancel) | any key | Stop your own login link working |
| [`cite_papers`](#cite_papers) | [`POST /api/cite`](api.md#post-apicite) | any key | Cite papers |
| [`cite_styles`](#cite_styles) | [`GET /api/cite/styles`](api.md#get-apicitestyles) | any key | The citation styles |
| [`content_badges`](#content_badges) | [`POST /api/papers/badges`](api.md#post-apipapersbadges) | any key | What is ready, for many papers |
| [`content_papers`](#content_papers) | [`GET /api/content/papers`](api.md#get-apicontentpapers) | any key | The papers a stage has not finished |
| [`content_status`](#content_status) | [`GET /api/content/status`](api.md#get-apicontentstatus) | any key | How far the content queue has got |
| [`create_my_login_link`](#create_my_login_link) | [`POST /api/account/login-link`](api.md#post-apiaccountlogin-link) | any key | A login link for yourself |
| [`get_list`](#get_list) | [`GET /api/lists/{slug}`](api.md#get-apilistsslug) | any key | Read a list |
| [`get_paper`](#get_paper) | [`GET /api/paper`](api.md#get-apipaper) | any key | One paper |
| [`get_paper_content`](#get_paper_content) | [`GET /api/paper/content`](api.md#get-apipapercontent) | any key | What is known about a paper |
| [`label_my_session`](#label_my_session) | [`POST /api/account/sessions/{session_id}/label`](api.md#post-apiaccountsessionssession_idlabel) | any key | Name one of your devices |
| [`library_status`](#library_status) | [`GET /api/library/status`](api.md#get-apilibrarystatus) | any key | How the library is doing |
| [`library_version`](#library_version) | [`GET /api/version`](api.md#get-apiversion) | any key | The library's version token |
| [`list_history`](#list_history) | [`GET /api/lists/{slug}/history`](api.md#get-apilistsslughistory) | any key | A list's past versions |
| [`list_lists`](#list_lists) | [`GET /api/lists`](api.md#get-apilists) | any key | List the lists |
| [`list_my_sessions`](#list_my_sessions) | [`GET /api/account/sessions`](api.md#get-apiaccountsessions) | any key | Your signed-in devices |
| [`list_ops`](#list_ops) | [`POST /api/lists/{slug}/ops`](api.md#post-apilistsslugops) | any key | Change a list |
| [`list_remaining`](#list_remaining) | [`GET /api/lists/{slug}/remaining`](api.md#get-apilistsslugremaining) | any key | Library papers not on a list |
| [`list_rows`](#list_rows) | [`GET /api/lists/{slug}/rows`](api.md#get-apilistsslugrows) | any key | A list as flat rows |
| [`list_schema`](#list_schema) | [`GET /api/lists/schema`](api.md#get-apilistsschema) | any key | List ops reference |
| [`list_team`](#list_team) | [`GET /api/team`](api.md#get-apiteam) | any key | List team |
| [`list_version`](#list_version) | [`GET /api/lists/{slug}/history/{rev}`](api.md#get-apilistsslughistoryrev) | any key | One past version of a list |
| [`missing_authors`](#missing_authors) | [`GET /api/missing/authors`](api.md#get-apimissingauthors) | any key | Who you cite most and lack |
| [`papers_exist`](#papers_exist) | [`POST /api/exists`](api.md#post-apiexists) | any key | Which of these papers are in the library |
| [`parse_refs`](#parse_refs) | [`POST /api/refs/parse`](api.md#post-apirefsparse) | any key | Read a reference list |
| [`recent_papers`](#recent_papers) | [`GET /api/papers/recent`](api.md#get-apipapersrecent) | any key | Papers added lately |
| [`rename_account`](#rename_account) | [`POST /api/account/rename`](api.md#post-apiaccountrename) | any key | Rename your account |
| [`retry_content`](#retry_content) | [`POST /api/papers/retry`](api.md#post-apipapersretry) | any key | Try a failed stage again |
| [`revoke_my_other_sessions`](#revoke_my_other_sessions) | [`POST /api/account/sessions/revoke-others`](api.md#post-apiaccountsessionsrevoke-others) | any key | Sign out all your devices |
| [`revoke_my_session`](#revoke_my_session) | [`POST /api/account/sessions/{session_id}/revoke`](api.md#post-apiaccountsessionssession_idrevoke) | any key | Sign out one of your devices |
| [`revoke_my_session_bulk`](#revoke_my_session_bulk) | [`POST /api/bulk/account/sessions/revoke`](api.md#post-apibulkaccountsessionsrevoke) | any key | Sign out one of your devices, for many at once |
| [`search_library`](#search_library) | [`GET /api/papers`](api.md#get-apipapers) | any key | Search the library |
| [`search_missing`](#search_missing) | [`GET /api/missing`](api.md#get-apimissing) | any key | Search the papers you do not have |
| [`set_shortcuts`](#set_shortcuts) | [`POST /api/account/shortcuts`](api.md#post-apiaccountshortcuts) | any key | Change your keyboard shortcuts |
| [`set_tag_colors`](#set_tag_colors) | [`POST /api/account/tag-colors`](api.md#post-apiaccounttag-colors) | any key | Choose where your tag colours come from |
| [`set_theme`](#set_theme) | [`POST /api/account/theme`](api.md#post-apiaccounttheme) | any key | Pick your theme |
| [`set_themes`](#set_themes) | [`POST /api/account/themes`](api.md#post-apiaccountthemes) | any key | Replace your own themes |
| [`skip_missing`](#skip_missing) | [`POST /api/missing/skip`](api.md#post-apimissingskip) | any key | Skip or unskip missing papers |
| [`whoami`](#whoami) | [`GET /api/me`](api.md#get-apime) | any key | Who am I |

## admin_cancel_login_link

Void an account's live login link without making a new one: a link that went somewhere it should not have. Devices it already signed in stay signed in; admin_revoke_access ends those too. Answers with removed: 0 or 1.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/cancel-login-link`](api.md#post-apiadminusersuser_idcancel-login-link) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_cancel_login_link_bulk

Runs admin_cancel_login_link once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/cancel-login-link`](api.md#post-apibulkadminuserscancel-login-link) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## admin_create_user

Make a new account and its first login link, to hand to the person. role is admin or user. Answers with user_id and the link. Answers with login_url (open it to sign in; it works once unless max_uses says otherwise), expires_at and max_uses. Any older link the account could still use stops working; its signed-in devices stay signed in. Revoking or deleting this API key voids the link while it is unused, and signs out every device it signed in.

|  |  |
|---|---|
| Route | [`POST /api/admin/users`](api.md#post-apiadminusers) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes | 1 to 80 characters |  |
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |
| `role` | string | yes | one of `admin`, `user` |  |

## admin_delete_user

Remove an account for good, with its sessions, login link and API keys. Cannot be undone: admin_set_user_disabled is the reversible version. Only the owner deletes an admin; nobody deletes the owner or themselves.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/delete`](api.md#post-apiadminusersuser_iddelete) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_delete_user_bulk

Runs admin_delete_user once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/delete`](api.md#post-apibulkadminusersdelete) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## admin_get_theme_defaults

The theme list everyone without their own list sees. themes is null while the built-in ones apply.

|  |  |
|---|---|
| Route | [`GET /api/admin/theme-defaults`](api.md#get-apiadmintheme-defaults) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## admin_list_user_sessions

Where an account is signed in: every session, with when it started and was last seen. Addresses are shown to the owner only, and only the owner sees the owner's.

|  |  |
|---|---|
| Route | [`GET /api/admin/users/{user_id}/sessions`](api.md#get-apiadminusersuser_idsessions) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_list_users

Accounts, a page at a time, including disabled ones, with each one's role and which is the owner. next is the offset of the following page, or null on the last one.

|  |  |
|---|---|
| Route | [`GET /api/admin/users`](api.md#get-apiadminusers) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `dir` | string | no | one of `asc`, `desc` | Default asc. |
| `limit` | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `q` | string | no |  | Keep accounts whose name or username contains this, in any case. |
| `sort` | string | no | one of `display_name`, `role`, `disabled`, `created_at` | Field to sort the whole list by. Rows without it go last. |

## admin_reissue_login

For someone who lost their device or their link: a fresh login link for their account. Answers with login_url (open it to sign in; it works once unless max_uses says otherwise), expires_at and max_uses. Any older link the account could still use stops working; its signed-in devices stay signed in. Revoking or deleting this API key voids the link while it is unused, and signs out every device it signed in.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/reissue-login`](api.md#post-apiadminusersuser_idreissue-login) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_rename_user

Change another account's display name (1-80 characters). Only the owner renames an admin. expect, when given, is the name you think it has now; if it changed meanwhile the rename is refused with the current name.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/rename`](api.md#post-apiadminusersuser_idrename) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes | 1 to 80 characters | 1-80 characters. |
| `expect` | string or null | no |  | The name you think they have. Answers 409 if it is another. |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_reset_two_factor

For someone who lost both their phone and their recovery codes: switches their two-factor sign-in off so a login link lets them in again. Only the owner resets an admin's; the owner's is reset from a shell.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/reset-two-factor`](api.md#post-apiadminusersuser_idreset-two-factor) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_reset_two_factor_bulk

Runs admin_reset_two_factor once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/reset-two-factor`](api.md#post-apibulkadminusersreset-two-factor) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## admin_revoke_access

For an account that may be compromised: ends every session and voids its live login link and every API key it holds, at once. The account stays enabled; admin_reissue_login lets its owner back in. The owner and your own account cannot be revoked.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/revoke-access`](api.md#post-apiadminusersuser_idrevoke-access) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_revoke_access_bulk

Runs admin_revoke_access once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/revoke-access`](api.md#post-apibulkadminusersrevoke-access) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## admin_revoke_user_session

End one of an account's sessions, rather than all of them with admin_revoke_access.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/sessions/{session_id}/revoke`](api.md#post-apiadminusersuser_idsessionssession_idrevoke) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_revoke_user_session_bulk

Runs admin_revoke_user_session once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/sessions/revoke`](api.md#post-apibulkadminuserssessionsrevoke) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## admin_set_theme_defaults

Replace the theme list everyone without their own list sees, 1 to 40 themes in the Theme schema of the API reference. null puts the built-in themes back.

|  |  |
|---|---|
| Route | [`POST /api/admin/theme-defaults`](api.md#post-apiadmintheme-defaults) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | no |  | Which built-in themes this list has seen: the highest since in Theme.builtIn (static/js/theme.js) when it was saved. Built-in themes added after that join the list the browser shows. Left out: 0, the first ones. |
| `themes` | array of object or null | no |  | 1 to 40 themes. null goes back to the built-in ones. |
| `themes[].accent` | string | yes |  | The main color: what you can press. |
| `themes[].background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].button` | object or null | no |  | How the theme's buttons look. A choice left out is the default (rounded, normal, raised, normal). |
| `themes[].button.case` | string | no | one of `normal`, `upper` |  |
| `themes[].button.depth` | string | no | one of `flat`, `raised`, `glossy` |  |
| `themes[].button.shape` | string | no | one of `square`, `soft`, `rounded`, `pill` |  |
| `themes[].button.weight` | string | no | one of `normal`, `medium`, `bold` |  |
| `themes[].dark` | object or null | no |  | A light theme's colors for dark mode, kept while it is light. Switching the theme to dark swaps them in. A light theme's light (or a dark theme's dark) is dropped. |
| `themes[].dark.accent` | string | yes |  | The main color: what you can press. |
| `themes[].dark.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].dark.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].dark.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].dark.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].id` | string | yes |  | Lower-case letters, digits, - and _, up to 32. |
| `themes[].light` | object or null | no |  | A dark theme's colors for light mode, kept while it is dark. Switching the theme to light swaps them in. |
| `themes[].light.accent` | string | yes |  | The main color: what you can press. |
| `themes[].light.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].light.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].light.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].light.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].mode` | string | yes | one of `light`, `dark` |  |
| `themes[].name` | string | yes |  | 1 to 60 characters. |
| `themes[].overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].surface` | string | no |  | Cards. Left out: the mode's own. |

## admin_set_user_disabled

Switch an account off (disabled: true) or back on (false). Disabling signs it out everywhere and voids its live login link; its API keys stop working while it is off. Reversible. The owner and your own account cannot be disabled.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/disabled`](api.md#post-apiadminusersuser_iddisabled) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `disabled` | boolean | yes |  |  |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_set_user_disabled_bulk

Runs admin_set_user_disabled once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/disabled`](api.md#post-apibulkadminusersdisabled) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].disabled` | boolean | no |  |  |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |
| `shared.disabled` | boolean | no |  |  |

## admin_set_user_role

Make an account an admin or an ordinary user. Only the owner takes an admin's rights away; the owner is always an admin, and nobody changes their own role. Becoming an admin ends the account's sessions and live login link.

|  |  |
|---|---|
| Route | [`POST /api/admin/users/{user_id}/role`](api.md#post-apiadminusersuser_idrole) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `role` | string | yes | one of `admin`, `user` |  |
| `user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |

## admin_set_user_role_bulk

Runs admin_set_user_role once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/admin/users/role`](api.md#post-apibulkadminusersrole) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].role` | string | no | one of `admin`, `user` |  |
| `items[].user_id` | integer | yes | at least 1 | The account's id, from GET /api/admin/users (admin_list_users over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |
| `shared.role` | string | no | one of `admin`, `user` |  |

## cancel_my_login_link

Void your account's live login link without making a new one. Devices it already signed in stay signed in. Answers with removed: 0 or 1.

|  |  |
|---|---|
| Route | [`POST /api/account/login-link/cancel`](api.md#post-apiaccountlogin-linkcancel) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## cite_papers

Each paper's in-text and full citation in a CSL style.

|  |  |
|---|---|
| Route | [`POST /api/cite`](api.md#post-apicite) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `keys` | array of string | yes |  | The papers' keys. At most 5000. |
| `list` | string | no |  | A list's slug: papers not in the library are cited from their row on it. |
| `style` | string | no |  | A CSL style from GET /api/cite/styles. Default: the list's, else library.cite_style. |

## cite_styles

The CSL styles on this server, usable or not (with why), and the default.

|  |  |
|---|---|
| Route | [`GET /api/cite/styles`](api.md#get-apicitestyles) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## content_badges

A short summary of each paper's content, for the badges on every row that shows a paper.

|  |  |
|---|---|
| Route | [`POST /api/papers/badges`](api.md#post-apipapersbadges) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `keys` | array of string | yes |  | Paper keys. At most 5000. |

## content_papers

A stage's papers in some states, a page at a time: the ones still to do, or the failures with why, when they first and last failed, and how many tries -- the Status and Errors screens.

|  |  |
|---|---|
| Route | [`GET /api/content/papers`](api.md#get-apicontentpapers) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `dir` | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `limit` | integer | no | 1 to 1000; default `100` | Rows to return. Default 100. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `q` | string | no |  | Only papers whose title, DOI or error contains this. |
| `sort` | string | no | one of `added`, `title`, `year`, `journal`, `state`, `error`, `attempts`, `first_failed`, `last_failed`; default `added` | Default added (newest first). |
| `stage` | string | no | one of `openalex`, `methods`, `code`, `datasets`, `modalities`; default `openalex` | The stage. |
| `state` | string | no | one of `unfinished`, `failed`, `not_found`, `errors`, `pending`, `done`; default `unfinished` | "unfinished" (default): pending, running and failed. "errors": failed and not found. |

## content_status

Per stage, how many papers are done, pending, running, failed or not found; the missing pool's size; what is running.

|  |  |
|---|---|
| Route | [`GET /api/content/status`](api.md#get-apicontentstatus) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## create_my_login_link

A link that signs your own account in on a browser or another device. An API key may ask only if your account let it, from a browser session (POST /api/keys/{key_id}/sign-in); its link works once, for at most 15 minutes. Only works if this key was allowed to make sign-in links, on the API keys card. Answers with login_url (open it to sign in; it works once, for at most 15 minutes), expires_at and max_uses. Any older link the account could still use stops working; its signed-in devices stay signed in. Revoking or deleting this API key voids the link while it is unused, and signs out every device it signed in.

|  |  |
|---|---|
| Route | [`POST /api/account/login-link`](api.md#post-apiaccountlogin-link) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expires_in_minutes` | integer or null | no | 0 to 525600 | 0 never expires. Default auth.login_token_ttl_seconds for a link that works once, auth.multi_use_login_token_ttl_seconds otherwise. |
| `max_uses` | integer or null | no | 0 to 1000 | Sign-ins the link allows: 1-1000, or 0 for unlimited. Default 1. |

## get_list

One list in full (a slug it was renamed away from answers the list as it is now): its document (rows in order, each with key, title, year, tags and cells; columns; the tag vocabulary with colours), its rev, and what the library knows of each row.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}`](api.md#get-apilistsslug) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

## get_paper

One paper in full: everything the library knows of it.

|  |  |
|---|---|
| Route | [`GET /api/paper`](api.md#get-apipaper) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | no |  | The paper's Zotero key, from search_library. |

## get_paper_content

Everything derived about one paper so far: its sections (the methods split), code and dataset links, modality tags, its OpenAlex network, and the state of each stage. Asking moves its unfinished stages to the front of the queue, so what someone is looking at is done first.

|  |  |
|---|---|
| Route | [`GET /api/paper/content`](api.md#get-apipapercontent) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | no |  | The paper's key, from search_library. |

## label_my_session

Give one of your devices a name (at most 80 characters; empty clears it). expect, when given, is the name you think it has now.

|  |  |
|---|---|
| Route | [`POST /api/account/sessions/{session_id}/label`](api.md#post-apiaccountsessionssession_idlabel) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `expect` | string or null | no |  | The name you think it has. Answers 409 if it has another. |
| `label` | string | yes | at most 80 characters | At most 80 characters. |
| `session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |

## library_status

Whether the catalogue has read Zotero yet, how many papers it holds, how many have their text indexed, and any error.

|  |  |
|---|---|
| Route | [`GET /api/library/status`](api.md#get-apilibrarystatus) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## library_version

A token that changes whenever the library does, so a userscript can poll cheaply and re-ask only then.

|  |  |
|---|---|
| Route | [`GET /api/version`](api.md#get-apiversion) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_history

The kept versions of a list (the last 40), newest first: rev, when, by whom, row and shelf counts. Version N is the list as it stood before the change that made rev N+1. list_version reads one in full. Restoring is done from the page.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}/history`](api.md#get-apilistsslughistory) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `200` | Versions to return. Default 200. |
| `offset` | integer | no | at least 0 | Versions to skip. |
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

## list_lists

Every curated list, the main one first: slug, name, rev (its version number), how many papers it holds, and whether it is view-only.

|  |  |
|---|---|
| Route | [`GET /api/lists`](api.md#get-apilists) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

## list_my_sessions

Where your account is signed in, a page at a time: id, when it started and was last seen, the browser, and the name you gave it. Through an API key no device is current. next is the offset of the following page, or null on the last one.

|  |  |
|---|---|
| Route | [`GET /api/account/sessions`](api.md#get-apiaccountsessions) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

## list_ops

Run a batch of ops against a list, atomically: every op succeeds and the list is saved once, or nothing is saved and the answer names the op that failed. Rows are named by key, DOI or "#N" (position). Examples: {"op":"add","paper":"<key or DOI or title>","at":"top"}, {"op":"move","row":"#12","to":1}, {"op":"tag","rows":["#1","#2"],"add":["premier"]}, {"op":"set_cell","row":"#1","col":"Notes","value":"key paper","mode":"append"}. dry_run previews; if_rev refuses the batch when the list moved since you read it. Every change keeps the previous version, so a removal can be put back.

|  |  |
|---|---|
| Route | [`POST /api/lists/{slug}/ops`](api.md#post-apilistsslugops) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `dry_run` | boolean | no |  | Preview: run the ops and answer, but save nothing. |
| `if_rev` | integer or null | no |  | Refuse the batch when the list has moved past this rev since you read it. |
| `ops` | array of object | yes |  | The ops, in order: {op, ...} each. GET /api/lists/schema names them all. |
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

## list_remaining

Every library paper not on the list (or its shelf), newest added first: what import_remaining picks from, in the order its range counts.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}/remaining`](api.md#get-apilistsslugremaining) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

## list_rows

The list as flat rows, each with its position and its cells under their column labels, filtered like the page's filter and tag bar.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}/rows`](api.md#get-apilistsslugrows) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 500; default `500` | Rows to return. Default 500. |
| `match` | string | no | one of `any`, `all`, `none`; default `any` | How the tags combine. Default any. |
| `offset` | integer | no | at least 0 | Rows to skip. |
| `q` | string | no |  | A text filter. Read up to 500 characters. |
| `shelf` | string | no |  | 1 or true: the staging shelf instead of the list. |
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |
| `tags` | string | no |  | Tags to filter by, comma-separated. |

## list_schema

Every op POST /api/lists/{slug}/ops takes, with its parameters, plus how rows and positions are named. Read it before a first list_ops call.

|  |  |
|---|---|
| Route | [`GET /api/lists/schema`](api.md#get-apilistsschema) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_team

People with an active account, a page at a time: id and display name. Use the id wherever another tool asks for a user. next is the offset of the following page, or null on the last one.

|  |  |
|---|---|
| Route | [`GET /api/team`](api.md#get-apiteam) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `200` | Rows to return. Default 200. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |

## list_version

One kept version of a list, with its whole document.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}/history/{rev}`](api.md#get-apilistsslughistoryrev) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `rev` | integer | yes | at least 1 | The version's rev, from list_history. |
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"). |

## missing_authors

The top 100 authors of the works your library cites and does not have, by summed connections then paper count.

|  |  |
|---|---|
| Route | [`GET /api/missing/authors`](api.md#get-apimissingauthors) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## papers_exist

The userscripts' question: which of these papers is in the library. A DOI settles it; a title is matched only without one. Called with an API key (Authorization: Bearer), so it needs no csrf_token; a browser session sends one like any other POST.

|  |  |
|---|---|
| Route | [`POST /api/exists`](api.md#post-apiexists) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `queries` | array of object | yes |  | The papers to look for: {"id", "title", "doi"} each. At most 5000. |

## parse_refs

A pasted or dropped reference list, read and matched to the library: a preview of what the stage op puts on the shelf.

|  |  |
|---|---|
| Route | [`POST /api/refs/parse`](api.md#post-apirefsparse) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `file` | string | no |  | Or a .docx or .txt file, base64. At most 10 MB. |
| `text` | string | no |  | A pasted reference list. |

## recent_papers

Papers added in Zotero in the last days, newest first, leaving out those already on the list not_on names: "what did I save this week that isn't on this list yet?". Read from the live catalogue, so a paper saved seconds ago is there.

|  |  |
|---|---|
| Route | [`GET /api/papers/recent`](api.md#get-apipapersrecent) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `days` | integer | no | 1 to 3650; default `7` | How far back. Default 7. |
| `limit` | integer | no | 1 to 1000; default `50` | Papers to return. Default 50. |
| `not_on` | string | no |  | A list's slug: leave out the papers already on it. |
| `offset` | integer | no | at least 0 | Papers to skip: the next value of the previous page. |

## rename_account

Change your own display name (1-80 characters). expect, when given, is the name you think it has now; if someone changed it meanwhile the rename is refused with the current name, so nothing is overwritten unseen.

|  |  |
|---|---|
| Route | [`POST /api/account/rename`](api.md#post-apiaccountrename) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `display_name` | string | yes | 1 to 80 characters |  |
| `expect` | string or null | no |  |  |

## retry_content

Put failed (and not-found) stages back in the queue at once: one paper's, one stage's across the library, or one paper's one stage. A not-found OpenAlex lookup is only ever asked again this way.

|  |  |
|---|---|
| Route | [`POST /api/papers/retry`](api.md#post-apipapersretry) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | no |  | A paper's key. Empty: every paper. |
| `stage` | string | no |  | One stage. Empty: every stage. |

## revoke_my_other_sessions

End every session your account has: through an API key there is no current device to keep, so every browser signs in again. API keys keep working. Answers with how many were removed.

|  |  |
|---|---|
| Route | [`POST /api/account/sessions/revoke-others`](api.md#post-apiaccountsessionsrevoke-others) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## revoke_my_session

End one of your signed-in sessions; that browser has to sign in again.

|  |  |
|---|---|
| Route | [`POST /api/account/sessions/{session_id}/revoke`](api.md#post-apiaccountsessionssession_idrevoke) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |

## revoke_my_session_bulk

Runs revoke_my_session once per item: items holds each call's arguments, shared the arguments they have in common (an item's own win). In order; one failing does not stop the rest, and the reply says how each went. At most 100 items.

|  |  |
|---|---|
| Route | [`POST /api/bulk/account/sessions/revoke`](api.md#post-apibulkaccountsessionsrevoke) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `items` | array of object | yes |  | One entry per thing to change: its id, and any field that differs from shared. |
| `items[].session_id` | string | yes |  | The device's id, from GET /api/account/sessions or GET /api/admin/users/{user_id}/sessions (list_my_sessions or admin_list_user_sessions over MCP). |
| `shared` | object | no |  | Fields every item gets, unless the item sets its own. |

## search_library

Search the papers in the Zotero library, a page at a time. mode "text" (default) is boolean full-text search over title, authors, abstract and the PDF's text: words are ANDed, OR between alternatives, -word or NOT word excludes, "a phrase" is literal. mode "title" finds a half-remembered title, typos and all, or a pasted DOI. Each paper's key is what list_ops' add takes.

|  |  |
|---|---|
| Route | [`GET /api/papers`](api.md#get-apipapers) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `dir` | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `has` | string | no |  | Only papers with: "code" (code links found), "data" (dataset links or names), "no_text" (no PDF text), "no_openalex" (OpenAlex has no record, or the lookup failed). Several, comma-separated, must all hold. |
| `limit` | integer | no | 1 to 1000; default `50` | Papers to return. Default 50. |
| `mode` | string | no | one of `text`, `title`; default `text` | "text" (default): boolean full-text search. "title": a half-remembered title, typos and all, or a DOI. |
| `offset` | integer | no | at least 0 | Papers to skip: the next value of the previous page. |
| `q` | string | no |  | The search. Empty lists every paper. Read up to 500 characters. |
| `sort` | string | no | one of `relevance`, `added`, `year`, `title`, `journal`, `authors`; default `relevance` | Default relevance. authors orders by the first author. |

## search_missing

The missing pool: works your library cites, and works citing it, that are not in the library, with how many of your papers connect to each. Searched with the library's grammar, sorted on several columns, a page at a time. It fills in as each paper's OpenAlex stage lands.

|  |  |
|---|---|
| Route | [`GET /api/missing`](api.md#get-apimissing) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 1000; default `100` | Rows to return. Default 100. |
| `offset` | integer | no | at least 0 | Rows to skip: the next value of the previous page. |
| `paper` | string | no |  | Only this library paper's network: its references and citers that you lack. |
| `pool` | string | no | one of `all`, `refs`, `citing`; default `all` | "all" (default), "refs" (works your library cites), "citing" (works citing your library). |
| `q` | string | no |  | The search, the library's boolean grammar. Read up to 500 characters. |
| `skipped` | string | no | one of `hide`, `show`; default `hide` | Default hide. |
| `sort` | string | no |  | Columns, most important first: "conn:desc,year:desc". Columns: relevance (only while searching), conn, cited_by, title, year. Default conn:desc. |

## set_shortcuts

Replace your changed keyboard shortcuts: action name to binding, such as "search": "Mod+K" (Mod is Cmd on a Mac, Ctrl elsewhere). Send the whole set; an empty binding switches a key off, and {} puts every key back to its default. whoami shows the current set.

|  |  |
|---|---|
| Route | [`POST /api/account/shortcuts`](api.md#post-apiaccountshortcuts) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `shortcuts` | map of string | yes |  | Action name to binding, such as "search": "Mod+K". Mod is Cmd on a Mac and Ctrl elsewhere. Only changed shortcuts are listed; an empty binding switches that key off. Replaces the whole set; {} puts every key back to its default. |

## set_tag_colors

Tags on lists are coloured from Wright State's palette (wsu), or from a gradient of the theme you use (theme). Only how you see them: what a list stores is unchanged.

|  |  |
|---|---|
| Route | [`POST /api/account/tag-colors`](api.md#post-apiaccounttag-colors) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `mode` | string | yes | one of `wsu`, `theme` | wsu: Wright State's palette (the default). theme: a gradient from the accent to the second colour of the theme you use. |

## set_theme

Switch to another theme from your list (or the defaults), by its id.

|  |  |
|---|---|
| Route | [`POST /api/account/theme`](api.md#post-apiaccounttheme) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `theme_id` | string | yes |  | A theme's id. Empty for the first in the list. |

## set_themes

Replace your whole list of color themes (1 to 40) and pick the one you use. themes: null goes back to following the app's defaults. A theme is the Theme schema in the API reference (config/api.json): id, name, mode light|dark, accent, second, and optional colors as #rrggbb. whoami shows the current list.

|  |  |
|---|---|
| Route | [`POST /api/account/themes`](api.md#post-apiaccountthemes) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `builtins` | integer | no |  | Which built-in themes this list has seen: the highest since in Theme.builtIn (static/js/theme.js) when it was saved. Built-in themes added after that join the list the browser shows. Left out: 0, the first ones. |
| `theme_id` | string | no |  | The theme you use. |
| `themes` | array of object or null | no |  | Your whole list, 1 to 40 themes. null goes back to following the app's defaults. |
| `themes[].accent` | string | yes |  | The main color: what you can press. |
| `themes[].background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].button` | object or null | no |  | How the theme's buttons look. A choice left out is the default (rounded, normal, raised, normal). |
| `themes[].button.case` | string | no | one of `normal`, `upper` |  |
| `themes[].button.depth` | string | no | one of `flat`, `raised`, `glossy` |  |
| `themes[].button.shape` | string | no | one of `square`, `soft`, `rounded`, `pill` |  |
| `themes[].button.weight` | string | no | one of `normal`, `medium`, `bold` |  |
| `themes[].dark` | object or null | no |  | A light theme's colors for dark mode, kept while it is light. Switching the theme to dark swaps them in. A light theme's light (or a dark theme's dark) is dropped. |
| `themes[].dark.accent` | string | yes |  | The main color: what you can press. |
| `themes[].dark.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].dark.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].dark.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].dark.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].id` | string | yes |  | Lower-case letters, digits, - and _, up to 32. |
| `themes[].light` | object or null | no |  | A dark theme's colors for light mode, kept while it is dark. Switching the theme to light swaps them in. |
| `themes[].light.accent` | string | yes |  | The main color: what you can press. |
| `themes[].light.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].light.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].light.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].light.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].mode` | string | yes | one of `light`, `dark` |  |
| `themes[].name` | string | yes |  | 1 to 60 characters. |
| `themes[].overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, info, infoBorder, border, and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].surface` | string | no |  | Cards. Left out: the mode's own. |

## skip_missing

Hide works from the Missing screen (a soft hide, undone by skip false), or bring them back.

|  |  |
|---|---|
| Route | [`POST /api/missing/skip`](api.md#post-apimissingskip) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `skip` | boolean | no | default `true` | true hides them (default); false shows them again. |
| `wids` | array of string | yes |  | OpenAlex ids ("W123"). At most 1000. |

## whoami

The account this API key belongs to, the role it acts with (role -- never higher than the key's own scope), and the account's own role.

|  |  |
|---|---|
| Route | [`GET /api/me`](api.md#get-apime) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## HTTP only

Routes an API key may call that have no tool, and why.

| Route | Why |
|---|---|
| [`GET /api/api.json`](api.md#get-apiapijson) | The API reference itself; GET /api/mcp.json is the MCP one. |
| [`GET /api/library/links`](api.md#get-apilibrarylinks) | Settings for drawing the page's links, not something an agent acts on. |
| [`GET /api/library/stream`](api.md#get-apilibrarystream) | A live event stream for the page; library_version is the polling equivalent. |
| [`GET /api/lists/deleted`](api.md#get-apilistsdeleted) | Which lists exist is a person's decision. |
| [`GET /api/lists/stream`](api.md#get-apilistsstream) | A live event stream for the page; get_list's rev says the same when asked. |
| [`GET /api/lists/{slug}/export.csv`](api.md#get-apilistsslugexportcsv) | A file to download; list_rows gives the same rows as data. |
| [`GET /api/mcp.json`](api.md#get-apimcpjson) | The MCP reference itself; tools/list gives the same list. |
| [`GET /api/paper/pdf`](api.md#get-apipaperpdf) | The file itself, for a browser to show. |
| [`POST /api/lists`](api.md#post-apilists) | An agent edits lists; which lists exist is a person's decision. |
| [`POST /api/lists/{slug}/delete`](api.md#post-apilistsslugdelete) | Which lists exist is a person's decision. |
| [`POST /api/lists/{slug}/export.csv`](api.md#post-apilistsslugexportcsv) | A file to download; list_rows gives the same rows as data. |
| [`POST /api/lists/{slug}/lock`](api.md#post-apilistssluglock) | Which lists may change is a person's decision. |
| [`POST /api/lists/{slug}/rename`](api.md#post-apilistsslugrename) | Which lists exist, and what they are called, is a person's decision. |
| [`POST /api/lists/{slug}/restore`](api.md#post-apilistsslugrestore) | Restoring is done from the page, by a person. |
| [`POST /api/lists/{slug}/undelete`](api.md#post-apilistsslugundelete) | Which lists exist is a person's decision. |
| [`POST /api/logout`](api.md#post-apilogout) | Ends a browser session; a key has none to end. |
| [`POST /api/logs/events`](api.md#post-apilogsevents) | The browser's own activity reports (track.js), not an action. |
| [`POST /api/sheet/csv`](api.md#post-apisheetcsv) | It reads a sheet for the page's import dialog; list_ops imports rows. |
| [`POST /mcp`](api.md#post-mcp) | The MCP endpoint itself. |
