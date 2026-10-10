# Appendix — `web` adapter, fresh held-out corpus, 2026-10-09

Companion to [MEASUREMENT-2026-10-09-web-adapter-fresh-held-out.md](./MEASUREMENT-2026-10-09-web-adapter-fresh-held-out.md). Sample: `random.Random(20261009).sample(findings, 60)`. TRUE = real hardcoded design value; FALSE = not a styling value (reason given).

## outline

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `app/scenes/Login/OAuthAuthorize.tsx:199` | spacing | TRUE | hardcoded styling value |
| 2 | `app/components/InputSelect.tsx:413` | css_spacing | TRUE | hardcoded styling value |
| 3 | `app/editor/components/FloatingToolbar.tsx:359` | css_spacing | TRUE | hardcoded styling value |
| 4 | `app/components/HoverPreview/Components.tsx:22` | css_spacing | TRUE | hardcoded styling value |
| 5 | `app/components/Sidebar/components/Header.tsx:151` | css_spacing | TRUE | hardcoded styling value |
| 6 | `app/components/DocumentListItem.tsx:311` | spacing | TRUE | hardcoded styling value |
| 7 | `app/components/InputColor.tsx:38` | css_spacing | TRUE | hardcoded styling value |
| 8 | `app/scenes/Login/Login.tsx:452` | css_spacing | TRUE | hardcoded styling value |
| 9 | `app/scenes/Drafts.tsx:105` | css_duration | TRUE | hardcoded styling value |
| 10 | `app/scenes/Document/components/ChangesNavigation.tsx:69` | css_spacing | TRUE | hardcoded styling value |
| 11 | `app/components/Notifications/AccessRequestActions.tsx:117` | css_spacing | TRUE | hardcoded styling value |
| 12 | `app/components/DropzoneContainer.tsx:31` | css_spacing | TRUE | hardcoded styling value |
| 13 | `app/scenes/Login/components/SwitchHostDialog.tsx:128` | css_spacing | TRUE | hardcoded styling value |
| 14 | `app/scenes/Login/Login.tsx:478` | css_spacing | TRUE | hardcoded styling value |
| 15 | `app/components/Reactions/Reaction.tsx:188` | css_spacing | TRUE | hardcoded styling value |
| 16 | `app/components/Reactions/ViewReactionsDialog.tsx:132` | spacing | TRUE | hardcoded styling value |
| 17 | `app/components/Sidebar/components/ResizeBorder.ts:35` | spacing | TRUE | hardcoded styling value |
| 18 | `app/components/Sharing/components/ShareSettingsPopover.tsx:411` | css_spacing | TRUE | hardcoded styling value |
| 19 | `app/scenes/Document/components/ChangesNavigation.tsx:76` | css_spacing | TRUE | hardcoded styling value |
| 20 | `app/components/Tooltip.tsx:286` | css_duration | TRUE | hardcoded styling value |
| 21 | `app/components/UnreadBadge.tsx:6` | css_spacing | TRUE | hardcoded styling value |
| 22 | `app/editor/components/Input.tsx:22` | css_spacing | TRUE | hardcoded styling value |
| 23 | `app/scenes/Document/components/SidebarLayout.tsx:97` | css_spacing | TRUE | hardcoded styling value |
| 24 | `app/components/CommandBar/CommandBar.tsx:98` | css_spacing | TRUE | hardcoded styling value |
| 25 | `app/scenes/Developer/Changesets.tsx:174` | css_spacing | TRUE | hardcoded styling value |
| 26 | `app/editor/components/FloatingToolbar.tsx:400` | css_spacing | TRUE | hardcoded styling value |
| 27 | `app/components/primitives/Drawer.tsx:97` | css_spacing | TRUE | hardcoded styling value |
| 28 | `app/components/InputSelect.tsx:422` | css_spacing | TRUE | hardcoded styling value |
| 29 | `app/editor/components/FindAndReplace.tsx:366` | spacing | TRUE | hardcoded styling value |
| 30 | `app/components/primitives/components/InputSelect.tsx:136` | css_spacing | TRUE | hardcoded styling value |
| 31 | `app/components/Input.tsx:384` | css_spacing | TRUE | hardcoded styling value |
| 32 | `app/scenes/Document/components/ConnectionStatus.tsx:87` | css_spacing | TRUE | hardcoded styling value |
| 33 | `app/scenes/Collection/components/Header.tsx:93` | css_spacing | TRUE | hardcoded styling value |
| 34 | `app/components/Sharing/Collection/AccessControlList.tsx:222` | spacing | TRUE | hardcoded styling value |
| 35 | `app/scenes/KeyboardShortcuts.tsx:478` | css_spacing | TRUE | hardcoded styling value |
| 36 | `app/scenes/Settings/components/UsersTable.tsx:187` | spacing | TRUE | hardcoded styling value |
| 37 | `app/components/Sidebar/components/ResizeBorder.ts:23` | css_duration | TRUE | hardcoded styling value |
| 38 | `app/scenes/Document/components/Comments/CommentThreadItem.tsx:392` | css_duration | TRUE | hardcoded styling value |
| 39 | `app/editor/components/FloatingToolbar.tsx:360` | css_spacing | TRUE | hardcoded styling value |
| 40 | `app/components/Table.tsx:648` | css_spacing | TRUE | hardcoded styling value |
| 41 | `app/components/Sidebar/components/Section.ts:12` | css_spacing | TRUE | hardcoded styling value |
| 42 | `app/components/Input.tsx:138` | spacing | TRUE | hardcoded styling value |
| 43 | `app/editor/components/SuggestionsMenu.tsx:1291` | css_spacing | TRUE | hardcoded styling value |
| 44 | `app/components/primitives/SplitButton.tsx:144` | spacing | TRUE | hardcoded styling value |
| 45 | `app/components/DocumentListItem.tsx:472` | css_spacing | TRUE | hardcoded styling value |
| 46 | `app/scenes/Settings/components/SharesTable.tsx:141` | spacing | TRUE | hardcoded styling value |
| 47 | `app/components/List/Item.tsx:203` | css_spacing | TRUE | hardcoded styling value |
| 48 | `app/editor/components/MediaDimension.tsx:311` | spacing | TRUE | hardcoded styling value |
| 49 | `app/scenes/Document/components/Comments/CommentThread.tsx:324` | css_spacing | TRUE | hardcoded styling value |
| 50 | `app/scenes/Document/components/Footer.tsx:65` | css_spacing | TRUE | hardcoded styling value |
| 51 | `app/scenes/Login/Login.tsx:439` | css_spacing | TRUE | hardcoded styling value |
| 52 | `app/components/Subheading.tsx:19` | css_spacing | TRUE | hardcoded styling value |
| 53 | `app/components/primitives/components/InputSelect.tsx:142` | css_spacing | TRUE | hardcoded styling value |
| 54 | `app/scenes/Document/components/ChangesNavigation.tsx:68` | css_spacing | TRUE | hardcoded styling value |
| 55 | `app/components/UnreadBadge.tsx:5` | css_spacing | TRUE | hardcoded styling value |
| 56 | `app/scenes/Document/components/ReferenceListItem.tsx:98` | css_spacing | TRUE | hardcoded styling value |
| 57 | `app/components/DropzoneContainer.tsx:18` | spacing | TRUE | hardcoded styling value |
| 58 | `app/components/primitives/SplitButton.tsx:233` | css_spacing | TRUE | hardcoded styling value |
| 59 | `app/components/Guide.tsx:47` | css_spacing | TRUE | hardcoded styling value |
| 60 | `app/components/EditableTitle.tsx:192` | css_spacing | TRUE | hardcoded styling value |

## gitea

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `web_src/css/repo.css:1640` | css_spacing | TRUE | hardcoded styling value |
| 2 | `web_src/js/components/DiffFileExtensionFilter.vue:130` | css_spacing | TRUE | hardcoded styling value |
| 3 | `web_src/css/features/console.css:352` | css_color | TRUE | hardcoded styling value |
| 4 | `web_src/css/modules/menu.css:9` | css_border_radius | TRUE | hardcoded styling value |
| 5 | `web_src/css/features/console.css:227` | css_color | TRUE | hardcoded styling value |
| 6 | `web_src/css/modules/codeeditor.css:467` | css_spacing | TRUE | hardcoded styling value |
| 7 | `web_src/css/features/colorpicker.css:36` | css_spacing | TRUE | hardcoded styling value |
| 8 | `web_src/css/features/console.css:337` | css_color | TRUE | hardcoded styling value |
| 9 | `web_src/css/repo.css:1521` | css_spacing | TRUE | hardcoded styling value |
| 10 | `web_src/css/repo.css:1237` | css_spacing | TRUE | hardcoded styling value |
| 11 | `web_src/css/modules/svg.css:39` | css_spacing | TRUE | hardcoded styling value |
| 12 | `web_src/js/utils/color.ts:23` | color | TRUE | hardcoded styling value |
| 13 | `web_src/js/components/RepoActionView.vue:385` | css_spacing | TRUE | hardcoded styling value |
| 14 | `web_src/css/features/projects.css:82` | css_spacing | TRUE | hardcoded styling value |
| 15 | `web_src/css/features/console.css:137` | css_color | TRUE | hardcoded styling value |
| 16 | `web_src/css/modules/menu.css:10` | css_spacing | TRUE | hardcoded styling value |
| 17 | `web_src/css/repo/commit-sign.css:6` | css_spacing | TRUE | hardcoded styling value |
| 18 | `web_src/js/components/RepoActionView.vue:374` | css_spacing | TRUE | hardcoded styling value |
| 19 | `web_src/css/repo.css:1621` | css_duration | TRUE | hardcoded styling value |
| 20 | `web_src/css/markup/content.css:117` | css_spacing | TRUE | hardcoded styling value |
| 21 | `web_src/css/markup/content.css:151` | css_spacing | TRUE | hardcoded styling value |
| 22 | `web_src/css/modules/container.css:30` | css_spacing | TRUE | hardcoded styling value |
| 23 | `web_src/css/modules/checkbox.css:25` | css_border_radius | TRUE | hardcoded styling value |
| 24 | `web_src/css/modules/svg.css:42` | css_spacing | TRUE | hardcoded styling value |
| 25 | `web_src/css/modules/dropdown.css:730` | css_border_radius | TRUE | hardcoded styling value |
| 26 | `web_src/css/modules/dropdown.css:758` | css_spacing | TRUE | hardcoded styling value |
| 27 | `web_src/css/modules/menu.css:294` | css_border_radius | TRUE | hardcoded styling value |
| 28 | `web_src/css/repo.css:1157` | css_spacing | TRUE | hardcoded styling value |
| 29 | `web_src/css/base.css:414` | css_spacing | TRUE | hardcoded styling value |
| 30 | `web_src/css/modules/shortcut.css:22` | css_spacing | TRUE | hardcoded styling value |
| 31 | `web_src/css/modules/menu.css:106` | css_spacing | TRUE | hardcoded styling value |
| 32 | `web_src/css/modules/form.css:55` | css_border_radius | TRUE | hardcoded styling value |
| 33 | `web_src/css/features/console.css:355` | css_color | TRUE | hardcoded styling value |
| 34 | `web_src/css/modules/label.css:205` | css_spacing | TRUE | hardcoded styling value |
| 35 | `web_src/css/modules/header.css:61` | css_spacing | TRUE | hardcoded styling value |
| 36 | `web_src/css/features/console.css:333` | css_color | TRUE | hardcoded styling value |
| 37 | `web_src/css/repo.css:109` | css_spacing | TRUE | hardcoded styling value |
| 38 | `web_src/css/modules/segment.css:159` | css_border_radius | TRUE | hardcoded styling value |
| 39 | `web_src/css/markup/content.css:361` | css_spacing | TRUE | hardcoded styling value |
| 40 | `web_src/js/components/WorkflowGraph.vue:662` | css_border_radius | TRUE | hardcoded styling value |
| 41 | `web_src/css/repo.css:1363` | css_spacing | TRUE | hardcoded styling value |
| 42 | `web_src/css/user.css:60` | css_spacing | TRUE | hardcoded styling value |
| 43 | `web_src/css/modules/comment.css:20` | css_spacing | TRUE | hardcoded styling value |
| 44 | `web_src/css/modules/tippy.css:151` | css_spacing | TRUE | hardcoded styling value |
| 45 | `web_src/css/modules/menu.css:40` | css_spacing | TRUE | hardcoded styling value |
| 46 | `web_src/css/modules/dropdown.css:203` | css_spacing | TRUE | hardcoded styling value |
| 47 | `web_src/css/modules/container.css:38` | css_spacing | TRUE | hardcoded styling value |
| 48 | `web_src/css/features/console.css:330` | css_color | TRUE | hardcoded styling value |
| 49 | `web_src/css/modules/message.css:11` | css_spacing | TRUE | hardcoded styling value |
| 50 | `web_src/css/modules/form.css:306` | css_spacing | TRUE | hardcoded styling value |
| 51 | `web_src/js/components/WorkflowGraph.vue:706` | css_spacing | TRUE | hardcoded styling value |
| 52 | `web_src/css/features/console.css:130` | css_color | TRUE | hardcoded styling value |
| 53 | `web_src/css/swagger-standalone.css:40` | css_spacing | TRUE | hardcoded styling value |
| 54 | `web_src/css/features/gitgraph.css:16` | css_spacing | TRUE | hardcoded styling value |
| 55 | `web_src/css/modules/menu.css:380` | css_spacing | TRUE | hardcoded styling value |
| 56 | `web_src/css/modules/table.css:66` | css_border_radius | TRUE | hardcoded styling value |
| 57 | `web_src/css/repo.css:282` | css_spacing | TRUE | hardcoded styling value |
| 58 | `web_src/css/repo.css:1445` | css_spacing | TRUE | hardcoded styling value |
| 59 | `web_src/css/modules/dropdown.css:120` | css_spacing | TRUE | hardcoded styling value |
| 60 | `web_src/css/modules/header.css:71` | css_spacing | TRUE | hardcoded styling value |

## open-webui

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `src/lib/components/layout/UpdateInfoToast.svelte:17` | tw_color | TRUE | hardcoded styling value |
| 2 | `src/lib/utils/index.ts:578` | color | TRUE | hardcoded styling value |
| 3 | `src/lib/components/chat/EmbeddedChatHistoryDropdown.svelte:95` | tw_spacing | TRUE | hardcoded styling value |
| 4 | `src/lib/components/chat/Messages/Skeleton.svelte:36` | css_duration | TRUE | hardcoded styling value |
| 5 | `src/lib/components/automations/AutomationEditor.svelte:381` | tw_spacing | TRUE | hardcoded styling value |
| 6 | `src/lib/components/chat/MessageInput.svelte:1907` | tw_spacing | TRUE | hardcoded styling value |
| 7 | `src/lib/components/admin/Settings/ExternalKnowledge.svelte:878` | tw_spacing | TRUE | hardcoded styling value |
| 8 | `src/lib/components/channel/Messages/Message.svelte:726` | css_color | TRUE | hardcoded styling value |
| 9 | `src/lib/components/layout/Sidebar/UserMenu.svelte:560` | tw_spacing | TRUE | hardcoded styling value |
| 10 | `src/lib/components/layout/Sidebar/RecursiveFolder.svelte:808` | tw_spacing | TRUE | hardcoded styling value |
| 11 | `src/lib/components/chat/SettingsModal.svelte:181` | tw_spacing | TRUE | hardcoded styling value |
| 12 | `src/lib/utils/pptxToHtml.ts:839` | color | FALSE | canvas fill in a PPTX→image preview renderer (document content, not UI chrome) |
| 13 | `src/lib/components/chat/FileNav/FilePreview.svelte:539` | tw_spacing | TRUE | hardcoded styling value |
| 14 | `src/lib/components/admin/Settings/Models.svelte:838` | tw_spacing | TRUE | hardcoded styling value |
| 15 | `src/lib/components/chat/Messages/StructuredOutputRenderer.svelte:67` | tw_spacing | TRUE | hardcoded styling value |
| 16 | `src/lib/components/notes/Notes/NoteMenu.svelte:70` | tw_spacing | TRUE | hardcoded styling value |
| 17 | `src/lib/utils/pptxToHtml.ts:815` | color | FALSE | canvas fill in a PPTX→image preview renderer (document content, not UI chrome) |
| 18 | `src/lib/components/layout/UpdateInfoToast.svelte:17` | tw_color | TRUE | hardcoded styling value |
| 19 | `src/lib/components/chat/FileNav/FilePreview.svelte:734` | css_spacing | TRUE | hardcoded styling value |
| 20 | `src/lib/components/chat/FileNav/FilePreview.svelte:748` | css_spacing | TRUE | hardcoded styling value |
| 21 | `src/lib/components/chat/MessageInput.svelte:2592` | tw_spacing | TRUE | hardcoded styling value |
| 22 | `src/lib/components/chat/FileNav/NotebookView.svelte:549` | css_color | TRUE | hardcoded styling value |
| 23 | `src/lib/components/chat/SettingsModal.svelte:516` | tw_spacing | TRUE | hardcoded styling value |
| 24 | `src/lib/components/chat/MessageInput/InputMenu/Chats.svelte:124` | tw_spacing | TRUE | hardcoded styling value |
| 25 | `src/lib/components/chat/MessageInput/InputMenu/Knowledge.svelte:278` | tw_spacing | TRUE | hardcoded styling value |
| 26 | `src/lib/components/chat/ModelSelector/ModelItemMenu.svelte:108` | tw_spacing | TRUE | hardcoded styling value |
| 27 | `src/lib/components/layout/Sidebar/Folders/FolderMenu.svelte:63` | tw_spacing | TRUE | hardcoded styling value |
| 28 | `src/app.css:755` | css_spacing | TRUE | hardcoded styling value |
| 29 | `src/lib/components/chat/Settings/Shortcuts.svelte:224` | tw_spacing | TRUE | hardcoded styling value |
| 30 | `src/lib/components/chat/Messages/UserMessage.svelte:357` | tw_spacing | TRUE | hardcoded styling value |
| 31 | `src/lib/components/chat/MessageInput/IntegrationsMenu.svelte:716` | tw_spacing | TRUE | hardcoded styling value |
| 32 | `src/lib/components/chat/EmbeddedChatHistoryItem.svelte:37` | tw_spacing | TRUE | hardcoded styling value |
| 33 | `src/lib/components/chat/Messages/ResponseMessage.svelte:900` | tw_spacing | TRUE | hardcoded styling value |
| 34 | `src/lib/components/chat/Messages/DiffBlock.svelte:144` | css_color | TRUE | hardcoded styling value |
| 35 | `src/lib/components/channel/Messages/Message.svelte:716` | css_color | TRUE | hardcoded styling value |
| 36 | `src/lib/components/common/PDFViewer.svelte:570` | tw_spacing | TRUE | hardcoded styling value |
| 37 | `src/lib/components/chat/Settings/Shortcuts.svelte:214` | tw_spacing | TRUE | hardcoded styling value |
| 38 | `src/lib/components/chat/FileNav/JsonTreeView.svelte:134` | css_color | TRUE | hardcoded styling value |
| 39 | `src/lib/components/layout/Sidebar/UserMenu.svelte:169` | tw_spacing | TRUE | hardcoded styling value |
| 40 | `src/lib/components/workspace/Prompts/PromptMenu.svelte:85` | tw_spacing | TRUE | hardcoded styling value |
| 41 | `src/lib/components/chat/MessageInput.svelte:2553` | tw_spacing | TRUE | hardcoded styling value |
| 42 | `src/lib/components/common/Drawer.svelte:87` | css_duration | TRUE | hardcoded styling value |
| 43 | `src/lib/components/chat/Messages/SubagentResultRow.svelte:40` | tw_spacing | TRUE | hardcoded styling value |
| 44 | `src/lib/components/chat/MessageInput/Commands/SlashCommands.svelte:175` | tw_spacing | TRUE | hardcoded styling value |
| 45 | `src/lib/components/chat/MessageInput.svelte:2665` | tw_spacing | TRUE | hardcoded styling value |
| 46 | `src/lib/components/channel/Messages/Message.svelte:707` | css_color | TRUE | hardcoded styling value |
| 47 | `src/lib/components/chat/ModelSelector/Selector.svelte:1280` | tw_spacing | TRUE | hardcoded styling value |
| 48 | `src/lib/components/chat/MessageInput/TerminalMenu.svelte:267` | tw_spacing | TRUE | hardcoded styling value |
| 49 | `src/lib/components/admin/Settings/Interface.svelte:246` | tw_spacing | TRUE | hardcoded styling value |
| 50 | `src/lib/components/workspace/Prompts/PromptHistoryMenu.svelte:65` | tw_spacing | TRUE | hardcoded styling value |
| 51 | `src/lib/components/chat/FileNav/FileCompare.svelte:317` | css_border_radius | TRUE | hardcoded styling value |
| 52 | `src/lib/components/chat/ModelSelector/Selector.svelte:960` | tw_spacing | TRUE | hardcoded styling value |
| 53 | `src/lib/components/chat/ShortcutItem.svelte:136` | tw_spacing | TRUE | hardcoded styling value |
| 54 | `src/lib/components/common/Select.svelte:32` | tw_spacing | TRUE | hardcoded styling value |
| 55 | `src/lib/components/layout/Sidebar/UserMenu.svelte:481` | tw_spacing | TRUE | hardcoded styling value |
| 56 | `src/lib/components/chat/MessageInput/Commands/Knowledge.svelte:158` | tw_spacing | TRUE | hardcoded styling value |
| 57 | `src/lib/components/chat/Messages/DiffBlock.svelte:155` | css_color | TRUE | hardcoded styling value |
| 58 | `src/lib/components/chat/Settings/UserSettingField.svelte:20` | tw_spacing | TRUE | hardcoded styling value |
| 59 | `src/lib/components/chat/MessageInput/InputMenu/Knowledge.svelte:203` | tw_spacing | TRUE | hardcoded styling value |
| 60 | `src/lib/components/layout/Sidebar/ChatMenu.svelte:314` | tw_spacing | TRUE | hardcoded styling value |

## jellyfin-web

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `src/components/playback/iconosd.scss:9` | css_color | TRUE | hardcoded styling value |
| 2 | `src/styles/librarybrowser.scss:472` | css_spacing | TRUE | hardcoded styling value |
| 3 | `src/components/indicators/indicators.scss:108` | css_spacing | TRUE | hardcoded styling value |
| 4 | `src/elements/emby-scrollbuttons/emby-scrollbuttons.scss:24` | css_spacing | TRUE | hardcoded styling value |
| 5 | `src/components/filterdialog/filterIndicator.scss:38` | css_spacing | TRUE | hardcoded styling value |
| 6 | `src/components/nowPlayingBar/nowPlayingBar.scss:62` | css_spacing | TRUE | hardcoded styling value |
| 7 | `src/styles/videoosd.scss:29` | css_color | TRUE | hardcoded styling value |
| 8 | `src/components/remotecontrol/remotecontrol.scss:176` | css_spacing | TRUE | hardcoded styling value |
| 9 | `src/components/guide/guide.scss:22` | css_spacing | TRUE | hardcoded styling value |
| 10 | `src/styles/librarybrowser.scss:473` | css_color | TRUE | hardcoded styling value |
| 11 | `src/components/subtitlesettings/subtitleappearancehelper.js:46` | color | TRUE | hardcoded styling value |
| 12 | `src/components/subtitlesettings/subtitleappearancehelper.js:49` | color | TRUE | hardcoded styling value |
| 13 | `src/elements/emby-select/emby-select.scss:95` | css_spacing | TRUE | hardcoded styling value |
| 14 | `src/elements/emby-checkbox/emby-checkbox.scss:10` | css_spacing | TRUE | hardcoded styling value |
| 15 | `src/styles/videoosd.scss:41` | css_color | TRUE | hardcoded styling value |
| 16 | `src/plugins/bookPlayer/style.scss:40` | css_spacing | TRUE | hardcoded styling value |
| 17 | `src/plugins/comicsPlayer/style.scss:2` | css_color | TRUE | hardcoded styling value |
| 18 | `src/styles/librarybrowser.scss:639` | css_spacing | TRUE | hardcoded styling value |
| 19 | `src/components/appFooter/appFooter.scss:7` | css_duration | TRUE | hardcoded styling value |
| 20 | `src/styles/site.scss:18` | css_duration | TRUE | hardcoded styling value |
| 21 | `src/styles/librarybrowser.scss:546` | css_color | TRUE | hardcoded styling value |
| 22 | `src/styles/dashboard.scss:36` | css_color | TRUE | hardcoded styling value |
| 23 | `src/components/playback/iconosd.scss:22` | css_spacing | TRUE | hardcoded styling value |
| 24 | `src/styles/librarybrowser.scss:299` | css_spacing | TRUE | hardcoded styling value |
| 25 | `src/styles/dashboard.scss:348` | css_spacing | TRUE | hardcoded styling value |
| 26 | `src/components/notifications/notifications.js:132` | spacing | FALSE | image-request parameter `getScaledImageUrl(id, { width: 80 })` (image metadata) |
| 27 | `src/themes/_base/theme.ts:11` | color | FALSE | MUI theme palette definition (`primary.main`) — token definition |
| 28 | `src/styles/metadataeditor.scss:45` | css_color | TRUE | hardcoded styling value |
| 29 | `src/components/subtitlesettings/subtitlesettings.js:73` | color | FALSE | default value of a user subtitle setting (user data) |
| 30 | `src/elements/emby-select/emby-select.scss:59` | css_duration | TRUE | hardcoded styling value |
| 31 | `src/styles/videoosd.scss:311` | css_color | TRUE | hardcoded styling value |
| 32 | `src/styles/librarybrowser.scss:478` | css_spacing | TRUE | hardcoded styling value |
| 33 | `src/elements/emby-tabs/emby-tabs.scss:14` | css_spacing | TRUE | hardcoded styling value |
| 34 | `src/elements/emby-select/emby-select.scss:105` | css_spacing | TRUE | hardcoded styling value |
| 35 | `src/components/metadataEditor/style.scss:17` | css_spacing | TRUE | hardcoded styling value |
| 36 | `src/styles/librarybrowser.scss:1022` | css_spacing | TRUE | hardcoded styling value |
| 37 | `src/styles/dashboard.scss:118` | css_spacing | TRUE | hardcoded styling value |
| 38 | `src/components/formdialog.scss:113` | css_spacing | TRUE | hardcoded styling value |
| 39 | `src/components/playerstats/playerstats.scss:33` | css_spacing | TRUE | hardcoded styling value |
| 40 | `src/styles/librarybrowser.scss:748` | css_spacing | TRUE | hardcoded styling value |
| 41 | `src/styles/videoosd.scss:157` | css_spacing | TRUE | hardcoded styling value |
| 42 | `src/themes/appletv/theme.scss:83` | css_color | TRUE | hardcoded styling value |
| 43 | `src/elements/emby-slider/emby-slider.scss:207` | css_color | TRUE | hardcoded styling value |
| 44 | `src/styles/dashboard.scss:372` | css_spacing | TRUE | hardcoded styling value |
| 45 | `src/styles/videoosd.scss:23` | css_spacing | TRUE | hardcoded styling value |
| 46 | `src/plugins/bookPlayer/style.scss:59` | css_color | TRUE | hardcoded styling value |
| 47 | `src/themes/purplehaze/theme.scss:223` | css_color | TRUE | hardcoded styling value |
| 48 | `src/components/formdialog.scss:135` | css_spacing | TRUE | hardcoded styling value |
| 49 | `src/styles/dashboard.scss:140` | css_spacing | TRUE | hardcoded styling value |
| 50 | `src/components/imageeditor/imageeditor.scss:27` | css_spacing | TRUE | hardcoded styling value |
| 51 | `src/components/guide/guide.scss:156` | css_border_radius | TRUE | hardcoded styling value |
| 52 | `src/styles/dashboard.scss:101` | css_border_radius | TRUE | hardcoded styling value |
| 53 | `src/themes/purplehaze/index.ts:22` | color | FALSE | MUI theme palette definition (`action.hover`) — token definition |
| 54 | `src/apps/legacy/features/search/components/searchfields.scss:8` | css_spacing | TRUE | hardcoded styling value |
| 55 | `src/styles/dashboard.scss:309` | css_spacing | TRUE | hardcoded styling value |
| 56 | `src/styles/librarybrowser.scss:1355` | css_spacing | TRUE | hardcoded styling value |
| 57 | `src/styles/librarybrowser.scss:1239` | css_spacing | TRUE | hardcoded styling value |
| 58 | `src/components/playback/iconosd.scss:8` | css_spacing | TRUE | hardcoded styling value |
| 59 | `src/components/actionSheet/actionSheet.scss:121` | css_spacing | TRUE | hardcoded styling value |
| 60 | `src/styles/librarybrowser.scss:1438` | css_spacing | TRUE | hardcoded styling value |

## twenty

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `packages/twenty-front/src/pages/settings/profile/SettingsTwoFactorAuthenticationMethod.tsx:50` | css_spacing | TRUE | hardcoded styling value |
| 2 | `packages/twenty-front/src/modules/object-record/record-field/ui/meta-types/input/components/RichTextFieldInput.tsx:43` | css_spacing | TRUE | hardcoded styling value |
| 3 | `packages/twenty-front/src/modules/side-panel/pages/email-block-settings/components/EmailAlignmentInput.tsx:27` | spacing | TRUE | hardcoded styling value |
| 4 | `packages/twenty-front/src/modules/blocknote-editor/components/BlockEditor.tsx:143` | css_spacing | TRUE | hardcoded styling value |
| 5 | `packages/twenty-front/src/modules/settings/accounts/components/SettingsAccountsVisibilityIcon.tsx:23` | css_spacing | TRUE | hardcoded styling value |
| 6 | `packages/twenty-front/src/modules/ai/components/LazyMarkdownRendererStyledComponents.tsx:116` | css_duration | FALSE | `1s` unit multiplier on a token (`calc(${duration.fast} * 1s)`) |
| 7 | `packages/twenty-front/src/modules/object-record/record-field/ui/form-types/components/FormMultiRecordPicker.tsx:36` | spacing | TRUE | hardcoded styling value |
| 8 | `packages/twenty-front/src/pages/settings/layout/SettingsLayoutViewDetail.tsx:93` | spacing | TRUE | hardcoded styling value |
| 9 | `packages/twenty-front/src/pages/settings/accounts/SettingsAccountsEditImapSmtpCaldavConnection.tsx:24` | css_spacing | TRUE | hardcoded styling value |
| 10 | `packages/twenty-front/src/modules/ui/input/components/internal/InputLabel/InputLabel.tsx:9` | css_spacing | TRUE | hardcoded styling value |
| 11 | `packages/twenty-front/src/modules/object-record/record-table/record-table-footer/components/RecordTableColumnAggregateFooterValueCell.tsx:46` | css_spacing | TRUE | hardcoded styling value |
| 12 | `packages/twenty-front/src/modules/ai/components/internal/AiChatContextUsageButton.tsx:42` | css_spacing | TRUE | hardcoded styling value |
| 13 | `packages/twenty-front/src/pages/settings/layout/SettingsLayoutViewDetail.tsx:127` | spacing | TRUE | hardcoded styling value |
| 14 | `packages/twenty-front/src/modules/onboarding/components/WelcomeOverlay/WelcomeOverlay.tsx:203` | css_spacing | TRUE | hardcoded styling value |
| 15 | `packages/twenty-front/src/modules/onboarding/components/WelcomeOverlay/WelcomeOverlay.tsx:210` | css_duration | TRUE | hardcoded styling value |
| 16 | `packages/twenty-front/src/modules/settings/accounts/components/message-folders/SettingsMessageFoldersBreadcrumb.tsx:15` | spacing | TRUE | hardcoded styling value |
| 17 | `packages/twenty-front/src/modules/page-layout/widgets/standalone-rich-text/components/DashboardColorIcon.tsx:14` | spacing | TRUE | hardcoded styling value |
| 18 | `packages/twenty-front/src/modules/ui/input/components/internal/date/components/DatePicker.tsx:67` | css_spacing | TRUE | hardcoded styling value |
| 19 | `packages/twenty-front/src/modules/settings/billing/components/internal/SettingsBillingSubscriptionInfoCard.tsx:153` | css_spacing | TRUE | hardcoded styling value |
| 20 | `packages/twenty-front/src/modules/settings/billing/hooks/useStripeAppearance.ts:57` | spacing | TRUE | hardcoded styling value |
| 21 | `packages/twenty-front/src/modules/side-panel/pages/search/components/SidePanelSearchRecordPreviewCard.tsx:92` | css_spacing | TRUE | hardcoded styling value |
| 22 | `packages/twenty-front/src/pages/ai-chat/AiChatPage.tsx:20` | css_spacing | FALSE | custom-property definition `--ai-chat-content-max-width` in a styled template |
| 23 | `packages/twenty-front/src/modules/advanced-text-editor/components/StyledBubbleMenuContainer.tsx:13` | css_spacing | TRUE | hardcoded styling value |
| 24 | `packages/twenty-front/src/modules/ui/input/components/BaseChip.tsx:44` | spacing | TRUE | hardcoded styling value |
| 25 | `packages/twenty-front/src/modules/side-panel/pages/email-block-settings/components/EmailColorInput.tsx:26` | css_spacing | TRUE | hardcoded styling value |
| 26 | `packages/twenty-front/src/modules/settings/data-model/fields/forms/select/components/SettingsDataModelFieldSelectFormOptionRow.tsx:78` | css_spacing | TRUE | hardcoded styling value |
| 27 | `packages/twenty-front/src/modules/object-record/record-index/components/RecordColumnResizeHandle.tsx:27` | spacing | TRUE | hardcoded styling value |
| 28 | `packages/twenty-front/src/modules/settings/usage/components/UsagePieChart.tsx:60` | spacing | TRUE | hardcoded styling value |
| 29 | `packages/twenty-front/src/modules/settings/experience/components/OpenRecordInCardMedia.tsx:57` | css_spacing | TRUE | hardcoded styling value |
| 30 | `packages/twenty-front/src/modules/object-record/record-field/ui/form-types/components/FormArrayFieldInput.tsx:63` | css_spacing | TRUE | hardcoded styling value |
| 31 | `packages/twenty-front/src/modules/ui/layout/dropdown/components/DropdownMenuSectionLabel.tsx:12` | css_spacing | TRUE | hardcoded styling value |
| 32 | `packages/twenty-front/src/modules/ui/field/input/components/TextAreaInput.tsx:49` | css_spacing | TRUE | hardcoded styling value |
| 33 | `packages/twenty-front/src/modules/onboarding/components/import-contacts/OnboardingImportPreviewEmails.tsx:165` | spacing | TRUE | hardcoded styling value |
| 34 | `packages/twenty-front/src/pages/settings/ai/components/SettingsToolIcon.tsx:82` | css_spacing | TRUE | hardcoded styling value |
| 35 | `packages/twenty-front/src/modules/settings/accounts/components/message-folders/SettingsAccountsMessageFoldersCard.tsx:31` | css_spacing | TRUE | hardcoded styling value |
| 36 | `packages/twenty-front/src/modules/ui/input/components/internal/date/components/StyledDatePickerContainer.tsx:113` | spacing | TRUE | hardcoded styling value |
| 37 | `packages/twenty-front/src/modules/side-panel/pages/email-block-settings/components/EmailAlignmentInput.tsx:30` | spacing | TRUE | hardcoded styling value |
| 38 | `packages/twenty-front/src/modules/settings/admin-panel/config-variables/components/SettingsAdminConfigVariables.tsx:25` | css_spacing | TRUE | hardcoded styling value |
| 39 | `packages/twenty-front/src/modules/settings/accounts/components/message-folders/SettingsMessageFoldersBreadcrumb.tsx:29` | spacing | TRUE | hardcoded styling value |
| 40 | `packages/twenty-front/src/modules/object-record/record-drag/components/RecordDragMultiDragCounterChip.tsx:9` | css_spacing | TRUE | hardcoded styling value |
| 41 | `packages/twenty-front/src/modules/spreadsheet-import/steps/components/ValidationStep/components/columns.tsx:83` | spacing | TRUE | hardcoded styling value |
| 42 | `packages/twenty-front/src/modules/settings/data-model/graph-overview/components/SettingsDataModelOverviewEffect.tsx:40` | spacing | FALSE | dagre graph-layout node size (layout-engine data) |
| 43 | `packages/twenty-front/src/modules/ai/components/ThinkingStepsDisplay.tsx:87` | css_spacing | TRUE | hardcoded styling value |
| 44 | `packages/twenty-front/src/modules/object-record/record-list/components/RecordListRecordGroupSection.tsx:22` | css_spacing | TRUE | hardcoded styling value |
| 45 | `packages/twenty-front/src/modules/spreadsheet-import/components/SpreadSheetImportModalCloseButton.tsx:11` | css_spacing | TRUE | hardcoded styling value |
| 46 | `packages/twenty-front/src/modules/ui/input/components/internal/date/components/DateTimePicker.tsx:81` | css_spacing | TRUE | hardcoded styling value |
| 47 | `packages/twenty-front/src/modules/ui/layout/tab-list/components/TabListHiddenMeasurements.tsx:29` | css_spacing | TRUE | hardcoded styling value |
| 48 | `packages/twenty-front/src/pages/settings/layout/SettingsLayoutPageLayoutDetail.tsx:94` | spacing | TRUE | hardcoded styling value |
| 49 | `packages/twenty-front/src/modules/settings/accounts/components/message-folders/SettingsMessageFoldersSkeletonLoader.tsx:33` | spacing | TRUE | hardcoded styling value |
| 50 | `packages/twenty-front/src/modules/settings/experience/components/OpenRecordInCardMedia.tsx:70` | css_spacing | TRUE | hardcoded styling value |
| 51 | `packages/twenty-front/src/modules/ui/input/components/TextInput.tsx:436` | css_spacing | TRUE | hardcoded styling value |
| 52 | `packages/twenty-front/src/modules/settings/billing/hooks/useStripeAppearance.ts:51` | spacing | TRUE | hardcoded styling value |
| 53 | `packages/twenty-front/src/modules/workflow/workflow-diagram/workflow-nodes/components/WorkflowNodeRightPart.tsx:10` | css_spacing | TRUE | hardcoded styling value |
| 54 | `packages/twenty-front/src/modules/ai/components/internal/AiChatContextUsageButton.tsx:39` | css_spacing | TRUE | hardcoded styling value |
| 55 | `packages/twenty-front/src/modules/settings/data-model/graph-overview/components/SettingsDataModelOverviewObject.tsx:81` | css_spacing | TRUE | hardcoded styling value |
| 56 | `packages/twenty-front/src/modules/auth/sign-in-up/components/internal/SignInUpWorkspaceCreationForm.tsx:137` | css_spacing | TRUE | hardcoded styling value |
| 57 | `packages/twenty-front/src/modules/ai/components/internal/AiChatEmailRecipientsRow.tsx:23` | css_spacing | TRUE | hardcoded styling value |
| 58 | `packages/twenty-front/src/modules/settings/data-model/graph-overview/components/SettingsDataModelOverviewEffect.tsx:34` | spacing | FALSE | dagre graph-layout node size (layout-engine data) |
| 59 | `packages/twenty-front/src/modules/views/view-picker/components/ViewPickerDropdown.tsx:39` | css_spacing | TRUE | hardcoded styling value |
| 60 | `packages/twenty-front/src/modules/activities/emails/recipients/components/EmailRecipientsFieldInput.tsx:89` | css_spacing | TRUE | hardcoded styling value |
