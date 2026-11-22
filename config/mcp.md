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
| [`cancel_summaries`](#cancel_summaries) | [`POST /api/summaries/cancel`](api.md#post-apisummariescancel) | any key | Empty the summaries queue |
| [`check_research_log`](#check_research_log) | [`POST /api/research-log/check`](api.md#post-apiresearch-logcheck) | any key | Which papers in a research log you lack |
| [`check_screener_rules`](#check_screener_rules) | [`POST /api/review/check`](api.md#post-apireviewcheck) | admin keys | Check screener rules without saving (admin) |
| [`cite_papers`](#cite_papers) | [`POST /api/cite`](api.md#post-apicite) | any key | Cite papers |
| [`cite_styles`](#cite_styles) | [`GET /api/cite/styles`](api.md#get-apicitestyles) | any key | The citation styles |
| [`content_badges`](#content_badges) | [`POST /api/papers/badges`](api.md#post-apipapersbadges) | any key | What is ready, for many papers |
| [`content_papers`](#content_papers) | [`GET /api/content/papers`](api.md#get-apicontentpapers) | any key | The papers a stage has not finished |
| [`content_status`](#content_status) | [`GET /api/content/status`](api.md#get-apicontentstatus) | any key | How far the content queue has got |
| [`crawl_status`](#crawl_status) | [`GET /api/crawl`](api.md#get-apicrawl) | any key | The crawl's progress and past runs |
| [`create_my_login_link`](#create_my_login_link) | [`POST /api/account/login-link`](api.md#post-apiaccountlogin-link) | any key | A login link for yourself |
| [`create_saved_search`](#create_saved_search) | [`POST /api/searches`](api.md#post-apisearches) | any key | Save a search |
| [`create_screener_setup`](#create_screener_setup) | [`POST /api/review/setups`](api.md#post-apireviewsetups) | admin keys | Make a rule setup (admin) |
| [`delete_saved_search`](#delete_saved_search) | [`POST /api/searches/{search}/delete`](api.md#post-apisearchessearchdelete) | any key | Delete a saved search |
| [`delete_screener_setup`](#delete_screener_setup) | [`POST /api/review/setups/{setup}/delete`](api.md#post-apireviewsetupssetupdelete) | admin keys | Delete a rule setup (admin) |
| [`delete_summary`](#delete_summary) | [`POST /api/summaries/delete`](api.md#post-apisummariesdelete) | any key | Delete a summary |
| [`figure_picks`](#figure_picks) | [`GET /api/figures/state`](api.md#get-apifiguresstate) | any key | A view's picks and skipped papers |
| [`get_crawl`](#get_crawl) | [`GET /api/crawl/{search}`](api.md#get-apicrawlsearch) | any key | A saved search's last crawl |
| [`get_list`](#get_list) | [`GET /api/lists/{slug}`](api.md#get-apilistsslug) | any key | Read a list |
| [`get_list_sheet`](#get_list_sheet) | [`GET /api/lists/{slug}/sheet`](api.md#get-apilistsslugsheet) | any key | A list's Google Sheet mirror |
| [`get_paper`](#get_paper) | [`GET /api/paper`](api.md#get-apipaper) | any key | One paper |
| [`get_paper_content`](#get_paper_content) | [`GET /api/paper/content`](api.md#get-apipapercontent) | any key | What is known about a paper |
| [`get_paper_summaries`](#get_paper_summaries) | [`GET /api/summaries/paper`](api.md#get-apisummariespaper) | any key | One paper's summaries |
| [`get_review`](#get_review) | [`GET /api/review/paper`](api.md#get-apireviewpaper) | any key | One paper's review with its evidence |
| [`get_review_missing_work`](#get_review_missing_work) | [`GET /api/review/missing/work`](api.md#get-apireviewmissingwork) | any key | One missing work's abstract screen |
| [`get_screener_setup`](#get_screener_setup) | [`GET /api/review/setups/{setup}`](api.md#get-apireviewsetupssetup) | admin keys | One rule setup (admin) |
| [`label_my_session`](#label_my_session) | [`POST /api/account/sessions/{session_id}/label`](api.md#post-apiaccountsessionssession_idlabel) | any key | Name one of your devices |
| [`library_status`](#library_status) | [`GET /api/library/status`](api.md#get-apilibrarystatus) | any key | How the library is doing |
| [`library_version`](#library_version) | [`GET /api/version`](api.md#get-apiversion) | any key | The library's version token |
| [`list_code`](#list_code) | [`GET /api/code`](api.md#get-apicode) | any key | Every paper that ships code |
| [`list_datasets`](#list_datasets) | [`GET /api/datasets`](api.md#get-apidatasets) | any key | What public data the library stands on |
| [`list_figures`](#list_figures) | [`GET /api/figures`](api.md#get-apifigures) | any key | Papers and their figures |
| [`list_history`](#list_history) | [`GET /api/lists/{slug}/history`](api.md#get-apilistsslughistory) | any key | A list's past versions |
| [`list_lists`](#list_lists) | [`GET /api/lists`](api.md#get-apilists) | any key | List the lists |
| [`list_my_sessions`](#list_my_sessions) | [`GET /api/account/sessions`](api.md#get-apiaccountsessions) | any key | Your signed-in devices |
| [`list_ops`](#list_ops) | [`POST /api/lists/{slug}/ops`](api.md#post-apilistsslugops) | any key | Change a list |
| [`list_remaining`](#list_remaining) | [`GET /api/lists/{slug}/remaining`](api.md#get-apilistsslugremaining) | any key | Library papers not on a list |
| [`list_review`](#list_review) | [`GET /api/review/library`](api.md#get-apireviewlibrary) | any key | The review of your curated papers |
| [`list_review_missing`](#list_review_missing) | [`GET /api/review/missing`](api.md#get-apireviewmissing) | any key | The review of the papers you do not have |
| [`list_review_overrides`](#list_review_overrides) | [`GET /api/review/overrides`](api.md#get-apireviewoverrides) | admin keys | Hand-checked review values (admin) |
| [`list_rows`](#list_rows) | [`GET /api/lists/{slug}/rows`](api.md#get-apilistsslugrows) | any key | A list as flat rows |
| [`list_saved_searches`](#list_saved_searches) | [`GET /api/searches`](api.md#get-apisearches) | any key | The saved searches |
| [`list_schema`](#list_schema) | [`GET /api/lists/schema`](api.md#get-apilistsschema) | any key | List ops reference |
| [`list_screener_setups`](#list_screener_setups) | [`GET /api/review/setups`](api.md#get-apireviewsetups) | admin keys | The screener's rule setups (admin) |
| [`list_team`](#list_team) | [`GET /api/team`](api.md#get-apiteam) | any key | List team |
| [`list_version`](#list_version) | [`GET /api/lists/{slug}/history/{rev}`](api.md#get-apilistsslughistoryrev) | any key | One past version of a list |
| [`missing_authors`](#missing_authors) | [`GET /api/missing/authors`](api.md#get-apimissingauthors) | any key | Who you cite most and lack |
| [`papers_exist`](#papers_exist) | [`POST /api/exists`](api.md#post-apiexists) | any key | Which of these papers are in the library |
| [`parse_refs`](#parse_refs) | [`POST /api/refs/parse`](api.md#post-apirefsparse) | any key | Read a reference list |
| [`pick_figures`](#pick_figures) | [`POST /api/figures/pick`](api.md#post-apifigurespick) | any key | Pick or unpick figures |
| [`recent_papers`](#recent_papers) | [`GET /api/papers/recent`](api.md#get-apipapersrecent) | any key | Papers added lately |
| [`rename_account`](#rename_account) | [`POST /api/account/rename`](api.md#post-apiaccountrename) | any key | Rename your account |
| [`reset_screener_setup`](#reset_screener_setup) | [`POST /api/review/setups/{setup}/reset`](api.md#post-apireviewsetupssetupreset) | admin keys | Reset the default rule setup (admin) |
| [`retry_content`](#retry_content) | [`POST /api/papers/retry`](api.md#post-apipapersretry) | any key | Try a failed stage again |
| [`revoke_my_other_sessions`](#revoke_my_other_sessions) | [`POST /api/account/sessions/revoke-others`](api.md#post-apiaccountsessionsrevoke-others) | any key | Sign out all your devices |
| [`revoke_my_session`](#revoke_my_session) | [`POST /api/account/sessions/{session_id}/revoke`](api.md#post-apiaccountsessionssession_idrevoke) | any key | Sign out one of your devices |
| [`revoke_my_session_bulk`](#revoke_my_session_bulk) | [`POST /api/bulk/account/sessions/revoke`](api.md#post-apibulkaccountsessionsrevoke) | any key | Sign out one of your devices, for many at once |
| [`run_saved_search`](#run_saved_search) | [`GET /api/searches/{search}/run`](api.md#get-apisearchessearchrun) | any key | Run a saved search |
| [`save_screener_setup`](#save_screener_setup) | [`POST /api/review/setups/{setup}`](api.md#post-apireviewsetupssetup) | admin keys | Save a rule setup (admin) |
| [`screener_progress`](#screener_progress) | [`GET /api/review/progress`](api.md#get-apireviewprogress) | admin keys | How far the screener has got (admin) |
| [`screener_rules_guide`](#screener_rules_guide) | [`GET /api/review/guide`](api.md#get-apireviewguide) | admin keys | How screener rules are written (admin) |
| [`search_library`](#search_library) | [`GET /api/papers`](api.md#get-apipapers) | any key | Search the library |
| [`search_missing`](#search_missing) | [`GET /api/missing`](api.md#get-apimissing) | any key | Search the papers you do not have |
| [`set_figure_picks`](#set_figure_picks) | [`POST /api/figures/replace`](api.md#post-apifiguresreplace) | any key | Replace a view's picks |
| [`set_list_sheet`](#set_list_sheet) | [`POST /api/lists/{slug}/sheet`](api.md#post-apilistsslugsheet) | any key | Mirror a list to a Google Sheet |
| [`set_review_override`](#set_review_override) | [`POST /api/review/overrides`](api.md#post-apireviewoverrides) | admin keys | Set a paper's hand-checked values (admin) |
| [`set_shortcuts`](#set_shortcuts) | [`POST /api/account/shortcuts`](api.md#post-apiaccountshortcuts) | any key | Change your keyboard shortcuts |
| [`set_tag_colors`](#set_tag_colors) | [`POST /api/account/tag-colors`](api.md#post-apiaccounttag-colors) | any key | Choose where your tag colours come from |
| [`set_theme`](#set_theme) | [`POST /api/account/theme`](api.md#post-apiaccounttheme) | any key | Pick your theme |
| [`set_themes`](#set_themes) | [`POST /api/account/themes`](api.md#post-apiaccountthemes) | any key | Replace your own themes |
| [`skip_figure_papers`](#skip_figure_papers) | [`POST /api/figures/skip`](api.md#post-apifiguresskip) | any key | Skip or unskip papers |
| [`skip_missing`](#skip_missing) | [`POST /api/missing/skip`](api.md#post-apimissingskip) | any key | Skip or unskip missing papers |
| [`start_crawl`](#start_crawl) | [`POST /api/crawl`](api.md#post-apicrawl) | any key | Start a crawl |
| [`stop_crawl`](#stop_crawl) | [`POST /api/crawl/stop`](api.md#post-apicrawlstop) | any key | Stop the crawl |
| [`summaries_rollup`](#summaries_rollup) | [`GET /api/summaries/rollup`](api.md#get-apisummariesrollup) | any key | One section's summaries as a table |
| [`summaries_status`](#summaries_status) | [`GET /api/summaries/status`](api.md#get-apisummariesstatus) | any key | The summaries queue |
| [`summarize_papers`](#summarize_papers) | [`POST /api/summaries`](api.md#post-apisummaries) | any key | Summarise papers |
| [`test_screener`](#test_screener) | [`POST /api/review/test`](api.md#post-apireviewtest) | admin keys | Try the screener on one paper (admin) |
| [`try_saved_search`](#try_saved_search) | [`POST /api/searches/try`](api.md#post-apisearchestry) | any key | Try a search before saving it |
| [`update_saved_search`](#update_saved_search) | [`POST /api/searches/{search}`](api.md#post-apisearchessearch) | any key | Change a saved search |
| [`use_screener_setup`](#use_screener_setup) | [`POST /api/review/setups/{setup}/activate`](api.md#post-apireviewsetupssetupactivate) | admin keys | Use a rule setup (admin) |
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
| `themes[].dark.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].dark.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].dark.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].id` | string | yes |  | Lower-case letters, digits, - and _, up to 32. |
| `themes[].light` | object or null | no |  | A dark theme's colors for light mode, kept while it is dark. Switching the theme to light swaps them in. |
| `themes[].light.accent` | string | yes |  | The main color: what you can press. |
| `themes[].light.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].light.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].light.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].light.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].mode` | string | yes | one of `light`, `dark` |  |
| `themes[].name` | string | yes |  | 1 to 60 characters. |
| `themes[].overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
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

## cancel_summaries

Drop every queued summary; the one being written finishes.

|  |  |
|---|---|
| Route | [`POST /api/summaries/cancel`](api.md#post-apisummariescancel) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## check_research_log

Reads a Markdown research log (# 03SEP2026 date headings, &nbsp;-separated blocks of a title line and its links), lifts each paper's DOI out of its links, and checks each the way /api/exists does: a DOI settles it, else the title. A DOI miss is retried by title and marked recovered.

|  |  |
|---|---|
| Route | [`POST /api/research-log/check`](api.md#post-apiresearch-logcheck) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `list_only` | boolean | no |  | Only what the parser extracted, unchecked: for a log whose layout drifted. |
| `name` | string | no | at most 200 characters; default `research log` | The file's name, for the report. |
| `text` | string | yes | at most 8388608 characters | The log's Markdown. |

## check_screener_rules

Whether rules load (every pattern compiles, every value has the right type): a whole document, a setup, or a setup with changes made. And how many papers using them would re-screen.

|  |  |
|---|---|
| Route | [`POST /api/review/check`](api.md#post-apireviewcheck) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `rules` | object or null | no |  | A whole rules document to check. |
| `setup` | string | no |  | A setup to check, or to make changes to first. |

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
| `stage` | string | no | one of `openalex`, `methods`, `code`, `datasets`, `modalities`, `figures`, `ocr`; default `openalex` | The stage. |
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

## crawl_status

Whether a crawl is running and how far it has got, and the last crawl of each saved search.

|  |  |
|---|---|
| Route | [`GET /api/crawl`](api.md#get-apicrawl) |
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

## create_saved_search

A new saved search. A search that does not hold together is a 400 listing each problem with where it is.

|  |  |
|---|---|
| Route | [`POST /api/searches`](api.md#post-apisearches) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `name` | string | yes | 1 to 120 characters | Its name, unique. |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |

## create_screener_setup

A new named setup: a copy of another (source), or a whole rules document (rules), with changes made to it. Rules that do not load are a 400 listing each problem with where it is; nothing is made. It is not used until activated.

|  |  |
|---|---|
| Route | [`POST /api/review/setups`](api.md#post-apireviewsetups) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `activate` | boolean | no |  | Use it at once (re-screens the candidate papers). |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `description` | string | no | at most 2000 characters | What it is for. |
| `name` | string | yes | 1 to 80 characters | Its name, unique. |
| `rules` | object or null | no |  | A whole rules document to start from instead of a copy. |
| `source` | string | no | default `default` | The setup to copy (default "default"). Ignored when rules are sent. |

## delete_saved_search

Delete a saved search. The answer is the search as it was, which POST /api/searches/restore puts back.

|  |  |
|---|---|
| Route | [`POST /api/searches/{search}/delete`](api.md#post-apisearchessearchdelete) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `search` | string | yes | 1 to 120 characters | The search's id, or its name. |

## delete_screener_setup

Deletes a setup for good. The default, and the setup in use, cannot be deleted.

|  |  |
|---|---|
| Route | [`POST /api/review/setups/{setup}/delete`](api.md#post-apireviewsetupssetupdelete) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `setup` | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

## delete_summary

Forget one paper's summary of one section.

|  |  |
|---|---|
| Route | [`POST /api/summaries/delete`](api.md#post-apisummariesdelete) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | yes | at least 1 characters |  |
| `section` | string | yes | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future` |  |

## figure_picks

Every picked figure (in pick order) and every skipped paper of one view.

|  |  |
|---|---|
| Route | [`GET /api/figures/state`](api.md#get-apifiguresstate) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `view` | string | no | one of `all`, `method`; default `all` | "all" (default): every figure. "method": the figures whose caption reads as a model design. |

## get_crawl

The works the last crawl for a saved search found, best score first.

|  |  |
|---|---|
| Route | [`GET /api/crawl/{search}`](api.md#get-apicrawlsearch) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 2000; default `500` |  |
| `search` | string | yes | 1 to 120 characters | The search's id, or its name. |
| `view` | string | no | one of `novel`, `visited`; default `novel` | "novel" (default): works you lack. "visited": every work walked. |

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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |

## get_list_sheet

Whether the list is mirrored to a Google Sheet, how, and how the last push and read-back went.

|  |  |
|---|---|
| Route | [`GET /api/lists/{slug}/sheet`](api.md#get-apilistsslugsheet) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `slug` | string | yes | 1 to 200 characters | The list's slug. |

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

## get_paper_summaries

Every summary kept for a paper, and those queued or failed.

|  |  |
|---|---|
| Route | [`GET /api/summaries/paper`](api.md#get-apisummariespaper) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | no |  | The paper's key. |

## get_review

One candidate paper's review in full: every extracted value with the sentence it came from, and the alternatives.

|  |  |
|---|---|
| Route | [`GET /api/review/paper`](api.md#get-apireviewpaper) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `key` | string | no | at most 200 characters | The paper's key. |

## get_review_missing_work

Screens one work of the Missing pool on its abstract: the verdict with its why, and every value the abstract states with its quote.

|  |  |
|---|---|
| Route | [`GET /api/review/missing/work`](api.md#get-apireviewmissingwork) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `wid` | string | no | at most 20 characters | The work's OpenAlex id (W...). |

## get_screener_setup

A setup's whole rules -- every word list, threshold, extraction field and dataset -- with config/review.yaml's defaults beside them and the paths where they differ.

|  |  |
|---|---|
| Route | [`GET /api/review/setups/{setup}`](api.md#get-apireviewsetupssetup) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `setup` | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

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

## list_code

One row per paper whose text links a code host, with each repository as GitHub or OSF describe it, the methods its README confirms or its citing papers suggest, and where the paper is curated.

|  |  |
|---|---|
| Route | [`GET /api/code`](api.md#get-apicode) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_datasets

One row per paper that links a data archive record or names a public collection (HCP, NSD, ...), each record with what its archive says it is. The Datasets screen also groups these by dataset.

|  |  |
|---|---|
| Route | [`GET /api/datasets`](api.md#get-apidatasets) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_figures

The papers whose figures have been cropped, with their figures, a page of papers at a time: every figure, or the method figures (captions matching config/method-images.txt). Each figure says whether it is picked in this view and in the other; chips, modality and keyword filters narrow the papers.

|  |  |
|---|---|
| Route | [`GET /api/figures`](api.md#get-apifigures) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `chip` | string | no | one of `all`, `lead`, `selected`, `skipped`, `other`; default `all` | all (default: every paper not skipped), lead (a structural term opens a caption), selected (a figure is picked), skipped, other (a figure is picked in the other view). |
| `dir` | string | no | one of `asc`, `desc`; default `desc` | Default desc. |
| `limit` | integer | no | 1 to 200; default `40` | Papers to return. Default 40. |
| `mod` | string | no |  | Only papers tagged with this modality. |
| `offset` | integer | no | at least 0 | Papers to skip: the next value of the previous page. |
| `q` | string | no |  | Only papers whose title, DOI or a caption contains this. |
| `sort` | string | no | one of `added`, `published`, `match`, `count`, `title`; default `added` | added (default: when it reached Zotero), published, match (best caption match), count (most figures), title. |
| `term` | string | no |  | Only papers with a caption matching this keyword (method view). |
| `view` | string | no | one of `all`, `method`; default `all` | "all" (default): every figure. "method": the figures whose caption reads as a model design. |

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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |

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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |

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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |

## list_review

Every paper on a list or with a picked figure, screened against the three inclusion criteria (fMRI dominant, decodes, attention in the authors' own model), with the values the screener extracted. Papers are screened one at a time as the content queue reaches them; those not reached yet are waiting.

|  |  |
|---|---|
| Route | [`GET /api/review/library`](api.md#get-apireviewlibrary) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_review_missing

The Missing pool screened on title and abstract alone with the same criteria, thresholds sized for an abstract: the works screened in, the near misses (failing exactly one criterion), the excluded tallied by reason, and how well the abstract screen agrees with the full-text one on your own papers. The pool is screened in the background as it fills; progress says how far.

|  |  |
|---|---|
| Route | [`GET /api/review/missing`](api.md#get-apireviewmissing) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## list_review_overrides

Values typed in by hand, by paper: each wins over what the screener extracted, whatever the setup, and flags the paper.

|  |  |
|---|---|
| Route | [`GET /api/review/overrides`](api.md#get-apireviewoverrides) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |
| `tags` | string | no |  | Tags to filter by, comma-separated. |

## list_saved_searches

Every saved search: a name, a boolean query and named groups of terms. The crawl and missing.xlsx use them.

|  |  |
|---|---|
| Route | [`GET /api/searches`](api.md#get-apisearches) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

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

## list_screener_setups

Every named set of screener rules, and which one is in use.

|  |  |
|---|---|
| Route | [`GET /api/review/setups`](api.md#get-apireviewsetups) |
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
| `slug` | string | yes |  | The list's slug, from GET /api/lists (the main list is "main"; "library" is every paper in Zotero, read-only). |

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

## pick_figures

Pick figures in one view (a new pick goes last), or take picks back.

|  |  |
|---|---|
| Route | [`POST /api/figures/pick`](api.md#post-apifigurespick) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `ids` | array of string | yes |  | Figure ids, "<paper key>#figure-N". At most 1000. |
| `pick` | boolean | no | default `true` | true picks them (default), false unpicks them. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

## recent_papers

Papers in order of when they were added to Zotero, newest first (only the last days, if days is set), leaving out those already on the list not_on names: "what did I save lately that isn't on this list yet?". Page through with offset and next. Read from the live catalogue, so a paper saved seconds ago is there.

|  |  |
|---|---|
| Route | [`GET /api/papers/recent`](api.md#get-apipapersrecent) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `days` | integer | no | 0 to 3650 | How far back, in days. 0 (default): every paper, newest first. |
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

## reset_screener_setup

Drops the default setup's edits: config/review.yaml as it is. Only the default can be reset.

|  |  |
|---|---|
| Route | [`POST /api/review/setups/{setup}/reset`](api.md#post-apireviewsetupssetupreset) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `setup` | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

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

## run_saved_search

The library papers and missing works a saved search matches, and how many each of its groups matches alone.

|  |  |
|---|---|
| Route | [`GET /api/searches/{search}/run`](api.md#get-apisearchessearchrun) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `limit` | integer | no | 1 to 2000; default `500` | Rows of each pool to return. Default 500, at most 2000. |
| `pool` | string | no | one of `library`, `missing`, `both`; default `both` | "both" (default), "library" or "missing". |
| `search` | string | yes | 1 to 120 characters | The search's id, or its name. |

## save_screener_setup

Changes a setup's rules (whole, or by changes), name or description. A pattern that does not compile, or a missing or wrong-typed value, is a 400 listing each problem with where it is; nothing is saved. Saving the setup in use re-screens the candidate papers one at a time; saving another re-screens nothing.

|  |  |
|---|---|
| Route | [`POST /api/review/setups/{setup}`](api.md#post-apireviewsetupssetup) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `base_signature` | string | no |  | The signature the setup had when read: if it has changed since, nothing is saved and the answer is a 409 with the current signature. |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `description` | string or null | no | at most 2000 characters | A new description (not for the default). |
| `name` | string or null | no | at most 80 characters | A new name (not for the default). |
| `rules` | object or null | no |  | The whole rules document. |
| `setup` | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

## screener_progress

Candidates, and how many are screened under the setup in use, waiting, or failed.

|  |  |
|---|---|
| Route | [`GET /api/review/progress`](api.md#get-apireviewprogress) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## screener_rules_guide

What an agent needs to write a setup: how patterns, macros and templates work, the change-path syntax, and the document's schema.

|  |  |
|---|---|
| Route | [`GET /api/review/guide`](api.md#get-apireviewguide) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

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

## set_figure_picks

Set a view's picks and skipped papers outright: Clear sends both empty, and its undo sends the old ones back.

|  |  |
|---|---|
| Route | [`POST /api/figures/replace`](api.md#post-apifiguresreplace) |
| Read only | no |
| Destructive | yes |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `selected` | array of string | no |  | The picks to keep, in order. |
| `skipped` | array of string | no |  | The skipped papers to keep. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

## set_list_sheet

Switch a list's Google Sheet mirror off, one-way or two-way; sync now; or overwrite the sheet with the list.

|  |  |
|---|---|
| Route | [`POST /api/lists/{slug}/sheet`](api.md#post-apilistsslugsheet) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `mode` | string or null | no | one of `off`, `one-way`, `two-way` | off; one-way (the list is pushed to its sheet after each change); two-way (also read back every poll_seconds). The first switch on makes the spreadsheet. |
| `overwrite` | boolean | no |  | Write the list over the sheet now, dropping anything typed there since the last read. |
| `slug` | string | yes | 1 to 200 characters | The list's slug. |
| `sync_now` | boolean | no |  | Push (and read back, two-way) now. |

## set_review_override

Replaces one paper's overrides; sending no fields removes them. Nothing is re-screened: overrides apply when read.

|  |  |
|---|---|
| Route | [`POST /api/review/overrides`](api.md#post-apireviewoverrides) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `fields` | map of string | yes |  | Field -> value. Empty values are dropped; none at all deletes the override. |
| `key` | string | yes | at least 1 characters | The paper's key (or its DOI). |

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
| `themes[].dark.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].dark.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].dark.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].id` | string | yes |  | Lower-case letters, digits, - and _, up to 32. |
| `themes[].light` | object or null | no |  | A dark theme's colors for light mode, kept while it is dark. Switching the theme to light swaps them in. |
| `themes[].light.accent` | string | yes |  | The main color: what you can press. |
| `themes[].light.background` | string | no |  | The page. Left out: the mode's own. |
| `themes[].light.overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].light.second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].light.surface` | string | no |  | Cards. Left out: the mode's own. |
| `themes[].mode` | string | yes | one of `light`, `dark` |  |
| `themes[].name` | string | yes |  | 1 to 60 characters. |
| `themes[].overrides` | map of string | no |  | Worked-out colors replaced by name: text, accent, accentFg, accentText, second, secondFg, secondText, link, navLink, background, surface, nested, chrome, bar (the bar across the top), barText, info, infoBorder, border, rowOdd and rowEven (alternating table rows), and for each button variant V (Secondary, Success, Danger, Warning, Info, Light, Dark) btnV, btnVFg and btnVText. Leaving one out puts the readable color back. |
| `themes[].second` | string | yes |  | Says where you are: active nav item, headings, info. |
| `themes[].surface` | string | no |  | Cards. Left out: the mode's own. |

## skip_figure_papers

Hide papers you are done with from one view, or bring them back.

|  |  |
|---|---|
| Route | [`POST /api/figures/skip`](api.md#post-apifiguresskip) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `keys` | array of string | yes |  | Paper keys. At most 1000. |
| `skip` | boolean | no | default `true` | true skips them (default), false brings them back. |
| `view` | string | yes | one of `all`, `method` | "all" or "method": each view has its own picks. |

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

## start_crawl

A best-first walk over OpenAlex from the library papers matching a saved search: score = keyword_weight x terms matched + cite_weight x log10(citations + 1) + link_weight x times reached. Runs in the background; GET /api/crawl says how far it has got, and the result replaces that search's last one.

|  |  |
|---|---|
| Route | [`POST /api/crawl`](api.md#post-apicrawl) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `api_budget` | integer | no | 0 to 20000; default `1000` | OpenAlex requests at most; 0 uses only what is cached. |
| `cite_weight` | number | no | 0 to 10; default `0.4` |  |
| `cited_by` | boolean | no | default `true` | Also walk forward, to the works citing each one. |
| `keyword_weight` | number | no | 0 to 10; default `1` |  |
| `link_weight` | number | no | 0 to 10; default `0.5` |  |
| `max_depth` | integer | no | 0 to 4; default `2` |  |
| `max_visits` | integer | no | 1 to 5000; default `500` |  |
| `min_novel_hits` | integer | no | 0 to 50; default `2` | Terms a work needs to be reported. |
| `min_seed_hits` | integer | no | 0 to 50; default `1` | Terms a library paper needs to be a seed. |
| `search` | string | yes | at least 1 characters | The saved search whose terms score the works (id or name). |

## stop_crawl

Stop the crawl under way; what it found so far is kept as its result.

|  |  |
|---|---|
| Route | [`POST /api/crawl/stop`](api.md#post-apicrawlstop) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## summaries_rollup

Every summary of a section: their subsection headers as columns, the hashtags and a histogram of them, and the extra keyword / regex columns config/rollup-extra-columns.yaml declares.

|  |  |
|---|---|
| Route | [`GET /api/summaries/rollup`](api.md#get-apisummariesrollup) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `section` | string | no | one of `all`, `abstract`, `introduction`, `background`, `methods`, `results`, `conclusions`, `future`; default `methods` | The section to roll up: all (the whole text), abstract, introduction, background, methods, results, conclusions or future. |

## summaries_status

Which language model writes the summaries, what is queued, and how many are kept per section.

|  |  |
|---|---|
| Route | [`GET /api/summaries/status`](api.md#get-apisummariesstatus) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|

## summarize_papers

Queue LLM summaries of these papers' sections. One call each, in the background, with config.yaml's llm: provider; each one costs money, so a section already summarised is skipped unless force. Progress arrives on the library stream as "summary" events.

|  |  |
|---|---|
| Route | [`POST /api/summaries`](api.md#post-apisummaries) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `force` | boolean | no |  | Summarise again a section already summarised. |
| `keys` | array of string | yes |  | Paper keys, at most 2000. |
| `sections` | array of string | yes |  | Sections to summarise: all (the whole text), abstract, introduction, background, methods, results, conclusions or future. |

## test_screener

Screens one library paper (key) or pasted text with the rules sent (unsaved), a setup, or the setup in use -- with changes made first, if sent -- and returns the verdict, why, and every extracted field with its quote. Nothing is stored.

|  |  |
|---|---|
| Route | [`POST /api/review/test`](api.md#post-apireviewtest) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `abstract` | string | no |  |  |
| `changes` | array of object or null | no |  | Changes to make to the setup's rules instead of sending them whole: [{path, value}] or [{path, remove: true}]. A change's path is how differences() names a place: keys joined by dots (thresholds.full.fmri_full_min.value), [name] for the item of a list whose name is that (extraction.fields[TR].patterns, datasets[NSD (Natural Scenes Dataset)]), [3] for an item by its place from 0, and [+] at the end to append. {path, value} sets it; {path, remove: true} takes it out. |
| `key` | string | no |  | A paper to screen, by its key. |
| `mode` | string | no | one of `full`, `abstract`; default `full` |  |
| `rules` | object or null | no |  | Rules to test with, not saved. |
| `setup` | string | no |  | A setup to test with (when no rules are sent); none means the one in use. |
| `text` | string | no |  | Pasted text to screen as the paper's body (and methods). |
| `title` | string | no |  |  |

## try_saved_search

Run a search as sent, without saving it: what the editor shows as you type.

|  |  |
|---|---|
| Route | [`POST /api/searches/try`](api.md#post-apisearchestry) |
| Read only | yes |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `limit` | integer | no | 1 to 2000; default `200` |  |
| `name` | string | no | at most 120 characters; default `Unsaved` |  |
| `pool` | string | no | one of `library`, `missing`, `both`; default `both` | "both" (default), "library" or "missing". |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |

## update_saved_search

Replace a saved search's name, query, groups and description.

|  |  |
|---|---|
| Route | [`POST /api/searches/{search}`](api.md#post-apisearchessearch) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `description` | string | no | at most 2000 characters |  |
| `groups` | array of object | no |  | Named groups of terms: {name (letters, digits, _), mode: any \| all \| none \| at_least, terms: [phrases] (any / all / none), n and of: [group names] (at_least), required (default true: the paper must match it)}. A term is matched as one word of the search box is: folded, its last word a prefix, in the title, authors, journal, tags, abstract or full text. |
| `name` | string | yes | 1 to 120 characters | Its name, unique. |
| `query` | string | no | at most 2000 characters | A boolean query in the search box's grammar (AND, OR, NOT, -term, "phrase"). May be empty. |
| `search` | string | yes | 1 to 120 characters | The search's id, or its name. |

## use_screener_setup

Screens with this setup from now on. Each candidate paper takes the result it already has for this setup's rules when its text has not changed, and is re-screened in the background otherwise.

|  |  |
|---|---|
| Route | [`POST /api/review/setups/{setup}/activate`](api.md#post-apireviewsetupssetupactivate) |
| Read only | no |
| Destructive | no |

**Arguments**

| Field | Type | Required | Limits | Description |
|---|---|---|---|---|
| `setup` | string | yes | 1 to 64 characters | The setup's id, from list_screener_setups ("default" is config/review.yaml). |

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
| [`GET /api/api.md`](api.md#get-apiapimd) | The API reference itself, for people; GET /api/api.json is the same as JSON. |
| [`GET /api/crawl/{search}/export.xlsx`](api.md#get-apicrawlsearchexportxlsx) | A file to download. |
| [`GET /api/figures/export`](api.md#get-apifiguresexport) | A file to download; figure_picks gives the ids as data. |
| [`GET /api/figures/image`](api.md#get-apifiguresimage) | An image, for a browser to show. |
| [`GET /api/ingest/target`](api.md#get-apiingesttarget) | For the Zotero plugin, which sends a paper's Zotero JSON and files; an agent has neither. |
| [`GET /api/library/links`](api.md#get-apilibrarylinks) | Settings for drawing the page's links, not something an agent acts on. |
| [`GET /api/library/stream`](api.md#get-apilibrarystream) | A live event stream for the page; library_version is the polling equivalent. |
| [`GET /api/lists/deleted`](api.md#get-apilistsdeleted) | Which lists exist is a person's decision. |
| [`GET /api/lists/export.zip`](api.md#get-apilistsexportzip) | A file to download; list_rows gives the same rows as data. |
| [`GET /api/lists/stream`](api.md#get-apilistsstream) | A live event stream for the page; get_list's rev says the same when asked. |
| [`GET /api/lists/{slug}/export.csv`](api.md#get-apilistsslugexportcsv) | A file to download; list_rows gives the same rows as data. |
| [`GET /api/mcp.json`](api.md#get-apimcpjson) | The MCP reference itself; tools/list gives the same list. |
| [`GET /api/mcp.md`](api.md#get-apimcpmd) | The MCP reference itself, for people; tools/list gives the same list. |
| [`GET /api/missing/export.xlsx`](api.md#get-apimissingexportxlsx) | A file to download. |
| [`GET /api/paper/pdf`](api.md#get-apipaperpdf) | The file itself, for a browser to show. |
| [`GET /api/paper/text`](api.md#get-apipapertext) | Plain text, for a browser to show. |
| [`GET /api/review/setups/{setup}/export`](api.md#get-apireviewsetupssetupexport) | A file to download; get_screener_setup gives the same rules as JSON. |
| [`GET /api/searches/{search}/export`](api.md#get-apisearchessearchexport) | A file to download. |
| [`GET /api/summaries/rollup.xlsx`](api.md#get-apisummariesrollupxlsx) | A file to download. |
| [`POST /api/export/xlsx`](api.md#post-apiexportxlsx) | A file to download, made from the rows sent. |
| [`POST /api/ingest/file`](api.md#post-apiingestfile) | For the Zotero plugin, which sends a paper's Zotero JSON and files; an agent has neither. |
| [`POST /api/ingest/items`](api.md#post-apiingestitems) | For the Zotero plugin, which sends a paper's Zotero JSON and files; an agent has neither. |
| [`POST /api/lists`](api.md#post-apilists) | An agent edits lists; which lists exist is a person's decision. |
| [`POST /api/lists/unzip`](api.md#post-apilistsunzip) | It reads a file for the page's import dialog; POST /api/lists makes the lists. |
| [`POST /api/lists/{slug}/delete`](api.md#post-apilistsslugdelete) | Which lists exist is a person's decision. |
| [`POST /api/lists/{slug}/export.csv`](api.md#post-apilistsslugexportcsv) | A file to download; list_rows gives the same rows as data. |
| [`POST /api/lists/{slug}/lock`](api.md#post-apilistssluglock) | Which lists may change is a person's decision. |
| [`POST /api/lists/{slug}/rename`](api.md#post-apilistsslugrename) | Which lists exist, and what they are called, is a person's decision. |
| [`POST /api/lists/{slug}/restore`](api.md#post-apilistsslugrestore) | Restoring is done from the page, by a person. |
| [`POST /api/lists/{slug}/undelete`](api.md#post-apilistsslugundelete) | Which lists exist is a person's decision. |
| [`POST /api/logout`](api.md#post-apilogout) | Ends a browser session; a key has none to end. |
| [`POST /api/logs/events`](api.md#post-apilogsevents) | The browser's own activity reports (track.js), not an action. |
| [`POST /api/searches/restore`](api.md#post-apisearchesrestore) | The page's undo; an agent makes the search again with create_saved_search. |
| [`POST /api/sheet/csv`](api.md#post-apisheetcsv) | It reads a sheet for the page's import dialog; list_ops imports rows. |
| [`POST /api/summaries/put`](api.md#post-apisummariesput) | The page's undo; an agent asks for the summary again with summarize_papers. |
| [`POST /mcp`](api.md#post-mcp) | The MCP endpoint itself. |
