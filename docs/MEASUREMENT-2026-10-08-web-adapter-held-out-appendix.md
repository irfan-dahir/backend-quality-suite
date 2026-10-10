# Appendix — per-finding classification, web adapter held-out measurement

Companion to [MEASUREMENT-2026-10-08-web-adapter-held-out.md](./MEASUREMENT-2026-10-08-web-adapter-held-out.md). Sample: `random.Random(20261008).sample(findings, 60)`. TRUE = real hardcoded design value; FALSE = not a styling value (reason given).

## mantine

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `packages/@mantine/core/src/components/PinInput/PinInput.story.tsx:156` | spacing | FALSE | story file (demo harness), not product UI |
| 2 | `packages/@mantine/core/src/components/Blockquote/Blockquote.story.tsx:9` | spacing | FALSE | story file (demo harness), not product UI |
| 3 | `packages/@mantine/core/src/components/TagsInput/TagsInput.story.tsx:130` | spacing | FALSE | story file (demo harness), not product UI |
| 4 | `packages/@mantine/core/src/components/ModalBase/ModalBase.story.tsx:22` | spacing | FALSE | story file (demo harness), not product UI |
| 5 | `packages/@mantine/core/src/components/Drawer/Drawer.story.tsx:60` | spacing | FALSE | story file (demo harness), not product UI |
| 6 | `packages/@mantine/core/src/components/Pill/Pill.story.tsx:219` | spacing | FALSE | story file (demo harness), not product UI |
| 7 | `packages/@mantine/core/src/components/Chip/Chip.story.tsx:103` | spacing | FALSE | story file (demo harness), not product UI |
| 8 | `packages/@mantine/core/src/components/Menu/Menu.module.css:98` | css_spacing | TRUE | hardcoded design value |
| 9 | `packages/@mantine/core/src/components/Progress/Progress.story.tsx:7` | spacing | FALSE | story file (demo harness), not product UI |
| 10 | `packages/@mantine/core/src/components/Menu/Menu.story.tsx:307` | border_radius | FALSE | story file (demo harness), not product UI |
| 11 | `packages/@mantine/core/src/components/Spoiler/Spoiler.story.tsx:57` | spacing | FALSE | story file (demo harness), not product UI |
| 12 | `packages/@mantine/core/src/components/ColorPicker/ColorPicker.story.tsx:118` | color | FALSE | story file (demo harness), not product UI |
| 13 | `packages/@mantine/core/src/core/MantineProvider/default-colors.ts:36` | color | FALSE | palette definition (default-colors.ts is the token source) |
| 14 | `packages/@mantine/core/src/components/Toggle/Toggle.story.tsx:31` | spacing | FALSE | story file (demo harness), not product UI |
| 15 | `packages/@mantine/core/src/components/AppShell/AppShell.story.tsx:435` | spacing | FALSE | story file (demo harness), not product UI |
| 16 | `packages/@mantine/core/src/components/Splitter/Splitter.story.tsx:23` | spacing | FALSE | story file (demo harness), not product UI |
| 17 | `packages/@mantine/core/src/components/Select/Select.story.tsx:162` | spacing | FALSE | story file (demo harness), not product UI |
| 18 | `packages/@mantine/core/src/components/Menubar/Menubar.story.tsx:120` | spacing | FALSE | story file (demo harness), not product UI |
| 19 | `packages/@mantine/core/src/components/Modal/Modal.story.tsx:402` | spacing | FALSE | story file (demo harness), not product UI |
| 20 | `packages/@mantine/core/src/components/PillsInput/PillsInput.story.tsx:162` | spacing | FALSE | story file (demo harness), not product UI |
| 21 | `packages/@mantine/core/src/components/ThemeIcon/ThemeIcon.story.tsx:65` | spacing | FALSE | story file (demo harness), not product UI |
| 22 | `packages/@mantine/core/src/components/Button/Button.story.tsx:255` | color | FALSE | story file (demo harness), not product UI |
| 23 | `packages/@mantine/core/src/components/Input/Input.module.css:178` | css_duration | TRUE | hardcoded design value |
| 24 | `packages/@mantine/core/src/components/ColorInput/ColorInput.story.tsx:27` | spacing | FALSE | story file (demo harness), not product UI |
| 25 | `packages/@mantine/core/src/core/MantineProvider/MantineProvider.story.tsx:35` | spacing | FALSE | story file (demo harness), not product UI |
| 26 | `packages/@mantine/core/src/components/PinInput/PinInput.story.tsx:121` | spacing | FALSE | story file (demo harness), not product UI |
| 27 | `packages/@mantine/core/src/components/Splitter/Splitter.story.tsx:109` | spacing | FALSE | story file (demo harness), not product UI |
| 28 | `packages/@mantine/core/src/components/Tour/Tour.story.tsx:141` | spacing | FALSE | story file (demo harness), not product UI |
| 29 | `packages/@mantine/core/src/components/Title/Title.story.tsx:7` | spacing | FALSE | story file (demo harness), not product UI |
| 30 | `packages/@mantine/core/src/components/Timeline/Timeline.story.tsx:434` | spacing | FALSE | story file (demo harness), not product UI |
| 31 | `packages/@mantine/core/src/components/Button/Button.story.tsx:237` | color | FALSE | story file (demo harness), not product UI |
| 32 | `packages/@mantine/core/src/components/Alert/Alert.module.css:79` | css_spacing | TRUE | hardcoded design value |
| 33 | `packages/@mantine/core/src/components/SegmentedControl/SegmentedControl.story.tsx:67` | spacing | FALSE | story file (demo harness), not product UI |
| 34 | `packages/@mantine/core/src/components/Checkbox/Checkbox.story.tsx:8` | spacing | FALSE | story file (demo harness), not product UI |
| 35 | `packages/@mantine/core/src/components/Tooltip/use-tooltip.ts:70` | spacing | TRUE | hardcoded design value |
| 36 | `packages/@mantine/core/src/components/Button/Button.story.tsx:322` | spacing | FALSE | story file (demo harness), not product UI |
| 37 | `packages/@mantine/core/src/components/RingProgress/RingProgress.story.tsx:87` | spacing | FALSE | story file (demo harness), not product UI |
| 38 | `packages/@mantine/core/src/core/MantineProvider/default-colors.ts:66` | color | FALSE | palette definition |
| 39 | `packages/@mantine/core/src/components/TreeSelect/TreeSelect.story.tsx:240` | color | FALSE | story file (demo harness), not product UI |
| 40 | `packages/@mantine/core/src/core/MantineProvider/default-colors.ts:148` | color | FALSE | palette definition |
| 41 | `packages/@mantine/core/src/components/Button/Button.story.tsx:381` | spacing | FALSE | story file (demo harness), not product UI |
| 42 | `packages/@mantine/core/src/components/Radio/Radio.story.tsx:132` | spacing | FALSE | story file (demo harness), not product UI |
| 43 | `packages/@mantine/core/src/components/Combobox/Combobox.module.css:222` | css_spacing | TRUE | hardcoded design value |
| 44 | `packages/@mantine/core/src/components/SegmentedControl/SegmentedControl.module.css:19` | css_spacing | TRUE | hardcoded design value |
| 45 | `packages/@mantine/core/src/components/Button/Button.story.tsx:71` | spacing | FALSE | story file (demo harness), not product UI |
| 46 | `packages/@mantine/core/src/components/Checkbox/CheckboxIndicator/CheckboxIndicator.story.tsx:10` | spacing | FALSE | story file (demo harness), not product UI |
| 47 | `packages/@mantine/core/src/components/ColorPicker/ColorPicker.story.tsx:114` | color | FALSE | story file (demo harness), not product UI |
| 48 | `packages/@mantine/core/src/components/Popover/Popover.story.tsx:62` | spacing | FALSE | story file (demo harness), not product UI |
| 49 | `packages/@mantine/core/src/components/Loader/Loader.module.css:35` | css_duration | TRUE | hardcoded design value |
| 50 | `packages/@mantine/core/src/components/NavLink/NavLink.story.tsx:90` | spacing | FALSE | story file (demo harness), not product UI |
| 51 | `packages/@mantine/core/src/components/FloatingIndicator/FloatingIndicator.module.css:10` | css_duration | FALSE | `0ms` reset, not a duration step |
| 52 | `packages/@mantine/core/src/components/Chip/Chip.story.tsx:43` | spacing | FALSE | story file (demo harness), not product UI |
| 53 | `packages/@mantine/core/src/components/Pill/Pill.module.css:75` | css_spacing | TRUE | hardcoded design value |
| 54 | `packages/@mantine/core/src/components/ActionIcon/ActionIcon.story.tsx:8` | spacing | FALSE | story file (demo harness), not product UI |
| 55 | `packages/@mantine/core/src/components/ColorPicker/ColorPicker.story.tsx:74` | spacing | FALSE | story file (demo harness), not product UI |
| 56 | `packages/@mantine/core/src/components/AppShell/AppShell.module.css:239` | css_spacing | TRUE | hardcoded design value |
| 57 | `packages/@mantine/core/src/components/TreeSelect/TreeSelect.story.tsx:240` | spacing | FALSE | story file (demo harness), not product UI |
| 58 | `packages/@mantine/core/src/components/Table/Table.story.tsx:242` | spacing | FALSE | story file (demo harness), not product UI |
| 59 | `packages/@mantine/core/src/components/AppShell/AppShell.story.tsx:434` | spacing | FALSE | story file (demo harness), not product UI |
| 60 | `packages/@mantine/core/src/components/Cascader/Cascader.module.css:151` | css_spacing | TRUE | hardcoded design value |

## immich (web/)

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `src/lib/components/shared-components/settings/SettingInputField.svelte:174` | css_spacing | TRUE | hardcoded design value |
| 2 | `src/lib/components/album-page/AlbumsTableHeader.svelte:41` | color | FALSE | HTML entity `&#8595;` read as a hex colour |
| 3 | `src/lib/managers/media-capabilities-manager.svelte.ts:28` | spacing | FALSE | video codec resolution data |
| 4 | `src/lib/components/server-statistics/ServerStatisticsCard.svelte:63` | css_duration | TRUE | hardcoded design value |
| 5 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:22` | spacing | FALSE | aspect-ratio option data |
| 6 | `src/lib/components/shared-components/settings/SettingInputField.svelte:92` | tw_spacing | TRUE | hardcoded design value |
| 7 | `src/lib/components/asset-viewer/PhotoViewer.svelte:264` | color | TRUE | hardcoded design value |
| 8 | `src/lib/components/asset-viewer/face-editor/FaceEditor.svelte:384` | tw_spacing | TRUE | hardcoded design value |
| 9 | `src/lib/components/shared-components/side-bar/ServerStatus.svelte:107` | tw_spacing | TRUE | hardcoded design value |
| 10 | `src/lib/components/assets/thumbnail/Thumbnail.svelte:407` | tw_color | TRUE | hardcoded design value |
| 11 | `src/lib/managers/media-capabilities-manager.svelte.ts:19` | spacing | FALSE | video codec resolution data |
| 12 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:18` | spacing | FALSE | aspect-ratio option data |
| 13 | `src/routes/admin/library-management/(list)/+layout.svelte:148` | css_border_radius | TRUE | hardcoded design value |
| 14 | `src/lib/modals/GeolocationPointPickerModal.svelte:176` | tw_color | TRUE | hardcoded design value |
| 15 | `src/lib/components/DelayedLoadingSpinner.svelte:18` | css_duration | TRUE | hardcoded design value |
| 16 | `src/lib/managers/media-capabilities-manager.svelte.ts:18` | spacing | FALSE | video codec resolution data |
| 17 | `src/lib/managers/edit/transform-manager.svelte.ts:231` | spacing | FALSE | image-dimension model state |
| 18 | `src/lib/components/memories/MemoryCard.svelte:85` | css_duration | TRUE | hardcoded design value |
| 19 | `src/lib/components/server-statistics/ServerStatisticsCard.svelte:61` | css_color | FALSE | mask-image alpha stops, not a colour |
| 20 | `src/lib/components/shared-components/settings/SettingInputField.svelte:173` | css_spacing | TRUE | hardcoded design value |
| 21 | `src/lib/managers/media-capabilities-manager.svelte.ts:30` | spacing | FALSE | video codec resolution data |
| 22 | `src/lib/components/asset-viewer/AssetViewer.svelte:716` | css_color | TRUE | hardcoded design value |
| 23 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:27` | spacing | FALSE | aspect-ratio option data |
| 24 | `src/lib/components/asset-viewer/SlideshowMetadataOverlay.svelte:46` | css_color | TRUE | hardcoded design value |
| 25 | `src/routes/NavigationLoadingBar.svelte:30` | tw_spacing | TRUE | hardcoded design value |
| 26 | `src/routes/auth/onboarding/+page.svelte:171` | tw_spacing | TRUE | hardcoded design value |
| 27 | `src/lib/managers/media-capabilities-manager.svelte.ts:19` | spacing | FALSE | video codec resolution data |
| 28 | `src/routes/(user)/buy/SupporterBadge.svelte:35` | css_color | TRUE | hardcoded design value |
| 29 | `src/lib/managers/media-capabilities-manager.svelte.ts:31` | spacing | FALSE | video codec resolution data |
| 30 | `src/routes/admin/library-management/(list)/+layout.svelte:161` | css_color | TRUE | hardcoded design value |
| 31 | `src/lib/components/asset-viewer/AssetViewer.svelte:711` | css_spacing | TRUE | hardcoded design value |
| 32 | `src/app.css:139` | css_border_radius | TRUE | hardcoded design value |
| 33 | `src/lib/managers/edit/transform-manager.svelte.ts:229` | spacing | FALSE | crop-region model state |
| 34 | `src/lib/components/asset-viewer/AssetViewer.svelte:728` | css_color | TRUE | hardcoded design value |
| 35 | `src/routes/(user)/buy/SupporterBadge.svelte:34` | css_color | TRUE | hardcoded design value |
| 36 | `src/lib/components/asset-viewer/AssetViewer.svelte:717` | css_border_radius | TRUE | hardcoded design value |
| 37 | `src/lib/managers/edit/transform-manager.svelte.ts:53` | spacing | FALSE | image-dimension model state |
| 38 | `src/routes/(user)/user-settings/SettingCombobox.svelte:38` | tw_spacing | TRUE | hardcoded design value |
| 39 | `src/lib/components/asset-viewer/AssetViewer.svelte:722` | css_color | TRUE | hardcoded design value |
| 40 | `src/lib/components/sidebar/Sidebar.svelte:42` | tw_spacing | TRUE | hardcoded design value |
| 41 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:19` | spacing | FALSE | aspect-ratio option data |
| 42 | `src/lib/managers/edit/transform-manager.svelte.ts:229` | spacing | FALSE | crop-region model state |
| 43 | `src/lib/components/asset-viewer/AssetViewer.svelte:710` | css_spacing | TRUE | hardcoded design value |
| 44 | `src/lib/components/asset-viewer/AssetViewer.svelte:729` | css_border_radius | TRUE | hardcoded design value |
| 45 | `src/lib/components/asset-viewer/editor/transform-tool/CropArea.svelte:184` | css_spacing | TRUE | hardcoded design value |
| 46 | `src/lib/components/shared-components/settings/SettingInputField.svelte:183` | css_border_radius | TRUE | hardcoded design value |
| 47 | `src/lib/components/asset-viewer/face-editor/FaceEditor.svelte:51` | spacing | TRUE | hardcoded design value |
| 48 | `src/lib/components/shared-components/navigation-bar/AccountInfoPanel.svelte:34` | tw_spacing | TRUE | hardcoded design value |
| 49 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:24` | spacing | FALSE | aspect-ratio option data |
| 50 | `src/lib/components/asset-viewer/PhotoSphereViewerAdapter.svelte:27` | color | TRUE | hardcoded design value |
| 51 | `src/lib/components/asset-viewer/editor/transform-tool/TransformTool.svelte:19` | spacing | FALSE | aspect-ratio option data |
| 52 | `src/routes/admin/library-management/(list)/+layout.svelte:166` | css_duration | TRUE | hardcoded design value |
| 53 | `src/app.css:112` | css_spacing | TRUE | hardcoded design value |
| 54 | `src/lib/components/asset-viewer/SlideshowMetadataOverlay.svelte:46` | css_color | TRUE | hardcoded design value |
| 55 | `src/lib/managers/media-capabilities-manager.svelte.ts:17` | spacing | FALSE | video codec resolution data |
| 56 | `src/routes/(user)/search/[[photos=photos]]/[[assetId=id]]/+page.svelte:270` | tw_spacing | TRUE | hardcoded design value |
| 57 | `src/routes/admin/server-status/ServerStatisticsPanel.svelte:196` | css_color | TRUE | hardcoded design value |
| 58 | `src/lib/components/shared-components/progress-bar/ProgressBar.svelte:94` | tw_spacing | TRUE | hardcoded design value |
| 59 | `src/routes/admin/server-status/ServerStatisticsPanel.svelte:225` | css_color | FALSE | mask-image alpha stops, not a colour |
| 60 | `src/routes/admin/queues/[name]/QueueGraph.svelte:109` | color | TRUE | hardcoded design value |

## mastodon

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `app/javascript/styles/mastodon/admin.scss:1675` | css_spacing | TRUE | hardcoded design value |
| 2 | `app/javascript/mastodon/components/form_fields/range_input.module.scss:25` | css_spacing | TRUE | hardcoded design value |
| 3 | `app/javascript/styles/mastodon/components.scss:3609` | css_spacing | TRUE | hardcoded design value |
| 4 | `app/javascript/styles/mastodon/admin.scss:92` | css_spacing | TRUE | hardcoded design value |
| 5 | `app/javascript/mastodon/utils/invoke_virtual_ios_keyboard.module.css:7` | css_spacing | TRUE | hardcoded design value |
| 6 | `app/javascript/styles/mastodon/admin.scss:1328` | css_spacing | TRUE | hardcoded design value |
| 7 | `app/javascript/mastodon/features/account_timeline/modals/styles.module.scss:75` | css_spacing | TRUE | hardcoded design value |
| 8 | `app/javascript/styles/mastodon/forms.scss:298` | css_spacing | TRUE | hardcoded design value |
| 9 | `app/javascript/styles/entrypoints/mailer.scss:914` | css_spacing | TRUE | hardcoded design value |
| 10 | `app/javascript/styles/mastodon/admin.scss:2103` | css_spacing | TRUE | hardcoded design value |
| 11 | `app/javascript/styles/mastodon/components.scss:10901` | css_spacing | TRUE | hardcoded design value |
| 12 | `app/javascript/styles/mastodon/forms.scss:196` | css_spacing | TRUE | hardcoded design value |
| 13 | `app/javascript/styles/entrypoints/mailer.scss:967` | css_spacing | TRUE | hardcoded design value |
| 14 | `app/javascript/styles/mastodon/components.scss:2434` | css_spacing | TRUE | hardcoded design value |
| 15 | `app/javascript/mastodon/features/collections/editor/styles.module.scss:78` | css_spacing | TRUE | hardcoded design value |
| 16 | `app/javascript/styles/mastodon/components.scss:7795` | css_spacing | TRUE | hardcoded design value |
| 17 | `app/javascript/styles/mastodon/forms.scss:1372` | css_spacing | TRUE | hardcoded design value |
| 18 | `app/javascript/styles/mastodon/components.scss:4381` | css_spacing | TRUE | hardcoded design value |
| 19 | `app/javascript/mastodon/components/callout/styles.module.css:18` | css_spacing | TRUE | hardcoded design value |
| 20 | `app/javascript/styles/mastodon/components.scss:2104` | css_spacing | TRUE | hardcoded design value |
| 21 | `app/javascript/styles/mastodon/components.scss:1199` | css_spacing | TRUE | hardcoded design value |
| 22 | `app/javascript/styles/entrypoints/mailer.scss:1059` | css_spacing | TRUE | hardcoded design value |
| 23 | `app/javascript/styles/mastodon/accounts.scss:202` | css_border_radius | TRUE | hardcoded design value |
| 24 | `app/javascript/styles/mastodon/admin.scss:1557` | css_spacing | TRUE | hardcoded design value |
| 25 | `app/javascript/styles/mastodon/components.scss:3920` | css_spacing | TRUE | hardcoded design value |
| 26 | `app/javascript/mastodon/components/status/quote.module.scss:64` | css_spacing | TRUE | hardcoded design value |
| 27 | `app/javascript/styles/entrypoints/mailer.scss:603` | css_color | TRUE | hardcoded design value |
| 28 | `app/javascript/mastodon/features/annual_report/announcement/styles.module.scss:13` | css_color | TRUE | hardcoded design value |
| 29 | `app/javascript/styles/mastodon/components.scss:7096` | css_spacing | TRUE | hardcoded design value |
| 30 | `app/javascript/styles/mastodon/admin.scss:1647` | css_spacing | TRUE | hardcoded design value |
| 31 | `app/javascript/styles/mastodon/components.scss:10348` | css_border_radius | TRUE | hardcoded design value |
| 32 | `app/javascript/styles/mastodon/components.scss:2215` | css_spacing | TRUE | hardcoded design value |
| 33 | `app/javascript/styles/mastodon/components.scss:5521` | css_spacing | TRUE | hardcoded design value |
| 34 | `app/javascript/styles/mastodon/components.scss:4242` | css_border_radius | TRUE | hardcoded design value |
| 35 | `app/javascript/styles/mastodon/components.scss:4215` | css_spacing | TRUE | hardcoded design value |
| 36 | `app/javascript/mastodon/components/status/attachments.module.scss:77` | css_duration | TRUE | hardcoded design value |
| 37 | `app/javascript/mastodon/components/account_header/styles.module.scss:156` | css_spacing | TRUE | hardcoded design value |
| 38 | `app/javascript/styles/mastodon/components.scss:839` | css_spacing | TRUE | hardcoded design value |
| 39 | `app/javascript/mastodon/features/account_edit/styles.module.scss:188` | css_spacing | TRUE | hardcoded design value |
| 40 | `app/javascript/styles/mastodon/polls.scss:29` | css_spacing | TRUE | hardcoded design value |
| 41 | `app/javascript/styles/mastodon/components.scss:5447` | css_spacing | TRUE | hardcoded design value |
| 42 | `app/javascript/mastodon/components/tags/style.module.css:31` | css_spacing | TRUE | hardcoded design value |
| 43 | `app/javascript/styles/mastodon/basics.scss:171` | css_spacing | TRUE | hardcoded design value |
| 44 | `app/javascript/styles/mastodon/components.scss:8129` | css_spacing | TRUE | hardcoded design value |
| 45 | `app/javascript/styles/mastodon/components.scss:6532` | css_spacing | TRUE | hardcoded design value |
| 46 | `app/javascript/styles/mastodon/components.scss:9047` | css_spacing | TRUE | hardcoded design value |
| 47 | `app/javascript/mastodon/features/account_edit/modals/styles.module.scss:93` | css_spacing | TRUE | hardcoded design value |
| 48 | `app/javascript/styles/mastodon/admin.scss:2290` | css_spacing | TRUE | hardcoded design value |
| 49 | `app/javascript/mastodon/features/compose/redesign/styles.module.scss:128` | css_duration | TRUE | hardcoded design value |
| 50 | `app/javascript/styles/mastodon/components.scss:743` | css_spacing | TRUE | hardcoded design value |
| 51 | `app/javascript/mastodon/components/form_fields/text_input.module.scss:8` | css_spacing | TRUE | hardcoded design value |
| 52 | `app/javascript/mastodon/features/account_featured/components/subheading.module.scss:7` | css_spacing | TRUE | hardcoded design value |
| 53 | `app/javascript/styles/mastodon/forms.scss:1034` | css_spacing | TRUE | hardcoded design value |
| 54 | `app/javascript/mastodon/features/collections/editor/styles.module.scss:20` | css_spacing | TRUE | hardcoded design value |
| 55 | `app/javascript/styles/mastodon/components.scss:10542` | css_spacing | TRUE | hardcoded design value |
| 56 | `app/javascript/styles/mastodon/admin.scss:1719` | css_spacing | TRUE | hardcoded design value |
| 57 | `app/javascript/styles/entrypoints/mailer.scss:711` | css_spacing | TRUE | hardcoded design value |
| 58 | `app/javascript/styles/mastodon/admin.scss:390` | css_spacing | TRUE | hardcoded design value |
| 59 | `app/javascript/styles/mastodon/emoji_picker.scss:36` | css_spacing | TRUE | hardcoded design value |
| 60 | `app/javascript/styles/entrypoints/mailer.scss:321` | css_spacing | TRUE | hardcoded design value |

## misskey

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `packages/frontend/src/components/MkOmit.vue:73` | css_color | TRUE | hardcoded design value |
| 2 | `packages/frontend/src/components/MkChannelPreview.vue:136` | css_color | TRUE | hardcoded design value |
| 3 | `packages/frontend/src/components/MkTutorialDialog.vue:137` | css_spacing | TRUE | hardcoded design value |
| 4 | `packages/frontend/src/components/MkNote.vue:793` | css_spacing | TRUE | hardcoded design value |
| 5 | `packages/frontend/src/components/MkImageFrameEditorDialog.vue:464` | css_spacing | TRUE | hardcoded design value |
| 6 | `packages/frontend/src/components/MkNoteSub.vue:164` | css_border_radius | TRUE | hardcoded design value |
| 7 | `packages/frontend/src/components/MkDonation.vue:25` | css_spacing | TRUE | hardcoded design value |
| 8 | `packages/frontend/src/pages/qr.show.vue:176` | css_spacing | TRUE | hardcoded design value |
| 9 | `packages/frontend/src/components/MkMenu.vue:807` | css_spacing | TRUE | hardcoded design value |
| 10 | `packages/frontend/src/components/MkPositionSelector.vue:47` | css_duration | TRUE | hardcoded design value |
| 11 | `packages/frontend/src/pages/settings/theme.vue:589` | css_spacing | TRUE | hardcoded design value |
| 12 | `packages/frontend/src/pages/gallery/edit.root.vue:123` | css_spacing | TRUE | hardcoded design value |
| 13 | `packages/frontend/src/pages/page.vue:369` | css_spacing | TRUE | hardcoded design value |
| 14 | `packages/frontend/src/components/MkModalWindow.vue:45` | spacing | TRUE | hardcoded design value |
| 15 | `packages/frontend/src/components/MkSuperMenu.vue:344` | css_spacing | TRUE | hardcoded design value |
| 16 | `packages/frontend/src/components/MkExtensionInstaller.vue:160` | css_spacing | TRUE | hardcoded design value |
| 17 | `packages/frontend/src/pages/admin/federation-job-queue.chart.vue:41` | css_spacing | TRUE | hardcoded design value |
| 18 | `packages/frontend/src/pages/settings/avatar-decoration.vue:162` | css_spacing | TRUE | hardcoded design value |
| 19 | `packages/frontend/src/components/MkUserPopup.vue:164` | css_border_radius | TRUE | hardcoded design value |
| 20 | `packages/frontend/src/components/MkAutocomplete.vue:484` | css_spacing | TRUE | hardcoded design value |
| 21 | `packages/frontend/src/components/MkStreamingNotesTimeline.vue:507` | css_color | FALSE | mask-image alpha stops, not a colour |
| 22 | `packages/frontend/src/components/MkRemoteEmojiEditDialog.vue:117` | css_spacing | TRUE | hardcoded design value |
| 23 | `packages/frontend/src/components/MkNote.vue:476` | css_spacing | TRUE | hardcoded design value |
| 24 | `packages/frontend/src/components/MkNote.vue:738` | css_spacing | TRUE | hardcoded design value |
| 25 | `packages/frontend/src/components/MkNotification.vue:450` | css_spacing | TRUE | hardcoded design value |
| 26 | `packages/frontend/src/components/MkUrlPreview.vue:310` | css_spacing | TRUE | hardcoded design value |
| 27 | `packages/frontend/src/components/MkChatHistories.vue:123` | css_spacing | TRUE | hardcoded design value |
| 28 | `packages/frontend/src/components/MkMediaImage.vue:258` | css_spacing | TRUE | hardcoded design value |
| 29 | `packages/frontend/src/components/MkDrive.file.vue:119` | css_color | TRUE | hardcoded design value |
| 30 | `packages/frontend/src/pages/admin/abuse-report/notification-recipient.item.vue:108` | css_spacing | TRUE | hardcoded design value |
| 31 | `packages/frontend/src/pages/user/home.vue:431` | css_spacing | TRUE | hardcoded design value |
| 32 | `packages/frontend/src/style.scss:510` | css_color | TRUE | hardcoded design value |
| 33 | `packages/frontend/src/components/MkNotification.vue:496` | css_spacing | TRUE | hardcoded design value |
| 34 | `packages/frontend/src/pages/drop-and-fusion.vue:163` | css_spacing | TRUE | hardcoded design value |
| 35 | `packages/frontend/src/components/MkSubNoteContent.vue:108` | css_spacing | TRUE | hardcoded design value |
| 36 | `packages/frontend/src/components/MkWaitingDialog.vue:47` | css_spacing | TRUE | hardcoded design value |
| 37 | `packages/frontend/src/components/MkUserOnlineIndicator.vue:43` | css_color | TRUE | hardcoded design value |
| 38 | `packages/frontend/src/components/MkUserInfo.vue:135` | css_spacing | TRUE | hardcoded design value |
| 39 | `packages/frontend/src/components/MkChartLegend.vue:83` | css_spacing | TRUE | hardcoded design value |
| 40 | `packages/frontend/src/components/MkAchievements.vue:149` | css_color | TRUE | hardcoded design value |
| 41 | `packages/frontend/src/pages/theme-editor.vue:118` | color | FALSE | theme-editor preset palette (data / definition) |
| 42 | `packages/frontend/src/components/MkReactionTooltip.vue:40` | css_spacing | TRUE | hardcoded design value |
| 43 | `packages/frontend/src/components/MkContainer.vue:251` | css_spacing | TRUE | hardcoded design value |
| 44 | `packages/frontend/src/pages/settings/mute-block.emoji-mute.vue:126` | css_spacing | TRUE | hardcoded design value |
| 45 | `packages/frontend/src/components/MkVisitorDashboard.vue:136` | css_spacing | TRUE | hardcoded design value |
| 46 | `packages/frontend/src/components/MkChatHistories.vue:204` | css_spacing | TRUE | hardcoded design value |
| 47 | `packages/frontend/src/components/MkPostForm.vue:1785` | css_spacing | TRUE | hardcoded design value |
| 48 | `packages/frontend/src/pages/theme-editor.vue:123` | color | FALSE | theme-editor preset palette (data / definition) |
| 49 | `packages/frontend/src/pages/admin/overview.ap-requests.vue:82` | color | TRUE | hardcoded design value |
| 50 | `packages/frontend/src/components/global/StackingRouterView.vue:220` | css_spacing | TRUE | hardcoded design value |
| 51 | `packages/frontend/src/pages/announcements.vue:28` | css_spacing | TRUE | hardcoded design value |
| 52 | `packages/frontend/src/components/MkCode.core.vue:146` | css_spacing | TRUE | hardcoded design value |
| 53 | `packages/frontend/src/components/MkPostForm.vue:1558` | css_spacing | TRUE | hardcoded design value |
| 54 | `packages/frontend/src/components/MkFlashPreview.vue:87` | css_spacing | TRUE | hardcoded design value |
| 55 | `packages/frontend/src/components/MkRange.vue:295` | css_border_radius | TRUE | hardcoded design value |
| 56 | `packages/frontend/src/pages/user/home.vue:677` | css_spacing | TRUE | hardcoded design value |
| 57 | `packages/frontend/src/components/MkChart.vue:103` | color | TRUE | hardcoded design value |
| 58 | `packages/frontend/src/components/MkCwButton.vue:46` | css_spacing | TRUE | hardcoded design value |
| 59 | `packages/frontend/src/pages/scratchpad.vue:265` | css_spacing | TRUE | hardcoded design value |
| 60 | `packages/frontend/src/components/MkEmojiPicker.vue:768` | css_color | TRUE | hardcoded design value |

## pi-hole/web

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `style/themes/default-darker.css:2369` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 2 | `style/pi-hole.css:851` | css_spacing | TRUE | hardcoded design value |
| 3 | `style/themes/default-darker.css:4314` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 4 | `style/themes/default-darker.css:1646` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 5 | `style/themes/default-darker.css:294` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 6 | `style/themes/default-darker.css:2185` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 7 | `style/pi-hole.css:1771` | css_color | TRUE | hardcoded design value |
| 8 | `style/themes/lcars.css:1347` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 9 | `style/themes/default-darker.css:1292` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 10 | `style/themes/default-darker.css:2689` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 11 | `style/themes/lcars.css:578` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 12 | `style/themes/lcars.css:1211` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 13 | `style/themes/default-darker.css:1351` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 14 | `style/themes/default-darker.css:3986` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 15 | `style/themes/default-dark.css:439` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 16 | `style/themes/default-light.css:309` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 17 | `style/themes/lcars.css:1995` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 18 | `style/themes/default-darker.css:4639` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 19 | `style/pi-hole.css:501` | css_duration | TRUE | hardcoded design value |
| 20 | `style/themes/default-darker.css:3860` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 21 | `style/themes/default-darker.css:3414` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 22 | `style/themes/default-darker.css:1437` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 23 | `style/themes/default-darker.css:1618` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 24 | `style/themes/default-darker.css:2272` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 25 | `style/themes/default-darker.css:4458` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 26 | `style/pi-hole.css:1164` | css_spacing | TRUE | hardcoded design value |
| 27 | `style/themes/default-darker.css:909` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 28 | `style/themes/default-dark.css:97` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 29 | `style/themes/default-light.css:122` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 30 | `style/themes/default-darker.css:2336` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 31 | `style/themes/lcars.css:344` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 32 | `style/themes/default-darker.css:3939` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 33 | `style/themes/default-darker.css:5076` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 34 | `style/themes/default-darker.css:4602` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 35 | `style/themes/default-darker.css:4587` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 36 | `style/pi-hole.css:1119` | css_spacing | TRUE | hardcoded design value |
| 37 | `scripts/js/settings-advanced.js:358` | spacing | TRUE | hardcoded design value |
| 38 | `style/themes/default-darker.css:3253` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 39 | `style/pi-hole.css:1506` | css_spacing | TRUE | hardcoded design value |
| 40 | `style/themes/lcars.css:2170` | css_spacing | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 41 | `style/themes/default-darker.css:5026` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 42 | `style/pi-hole.css:1286` | css_color | TRUE | hardcoded design value |
| 43 | `style/themes/default-darker.css:2911` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 44 | `style/themes/high-contrast-dark.css:286` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 45 | `style/themes/default-darker.css:5499` | css_spacing | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 46 | `style/themes/high-contrast-dark.css:804` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 47 | `style/pi-hole.css:1362` | css_spacing | TRUE | hardcoded design value |
| 48 | `style/themes/default-darker.css:2798` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 49 | `style/themes/default-dark.css:540` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 50 | `style/themes/default-darker.css:3206` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 51 | `style/pi-hole.css:999` | css_border_radius | TRUE | hardcoded design value |
| 52 | `style/pi-hole.css:1645` | css_color | TRUE | hardcoded design value |
| 53 | `style/themes/lcars.css:1821` | css_spacing | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 54 | `style/themes/default-dark.css:416` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 55 | `style/themes/lcars.css:445` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 56 | `style/themes/default-darker.css:2392` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 57 | `style/themes/default-darker.css:994` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 58 | `style/themes/default-darker.css:1737` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 59 | `style/themes/lcars.css:935` | css_spacing | TRUE | hardcoded design value (theme stylesheet, no token layer) |
| 60 | `style/themes/default-darker.css:632` | css_color | TRUE | hardcoded design value (theme stylesheet, no token layer) |

## cal.com

| # | File:line | Kind | Verdict | Reason |
|---|---|---|---|---|
| 1 | `apps/web/modules/calendars/weeklyview/components/event/Event.tsx:130` | tw_spacing | TRUE | hardcoded design value |
| 2 | `apps/web/components/AddToHomescreen.tsx:23` | tw_color | TRUE | hardcoded design value |
| 3 | `apps/web/modules/event-types/components/SkeletonLoader.tsx:57` | tw_border_radius | TRUE | hardcoded design value |
| 4 | `apps/web/modules/bookings/components/event-meta/Duration.tsx:129` | tw_border_radius | TRUE | hardcoded design value |
| 5 | `apps/web/modules/api-keys/api-keys/components/ApiKeyDialogForm.tsx:225` | spacing | TRUE | hardcoded design value |
| 6 | `apps/web/modules/calendars/weeklyview/components/event/Empty.tsx:209` | tw_border_radius | TRUE | hardcoded design value |
| 7 | `apps/web/components/apps/make/Setup.tsx:153` | tw_spacing | TRUE | hardcoded design value |
| 8 | `apps/web/modules/shell/navigation/NavigationItem.tsx:213` | tw_spacing | TRUE | hardcoded design value |
| 9 | `apps/web/modules/bookings/components/HavingTroubleFindingTime.tsx:31` | tw_border_radius | TRUE | hardcoded design value |
| 10 | `apps/web/modules/embed/components/Embed.tsx:386` | tw_spacing | TRUE | hardcoded design value |
| 11 | `apps/web/modules/videos/views/videos-meeting-ended-single-view.tsx:23` | color | FALSE | HTML entity `&#8203;` read as a hex colour |
| 12 | `apps/web/modules/settings/outOfOffice/OutOfOfficeEntriesList.tsx:358` | tw_spacing | TRUE | hardcoded design value |
| 13 | `apps/web/modules/shell/navigation/Navigation.tsx:116` | tw_spacing | TRUE | hardcoded design value |
| 14 | `apps/web/modules/bookings/components/OutOfOfficeInSlots.tsx:68` | tw_spacing | TRUE | hardcoded design value |
| 15 | `apps/web/modules/event-types/components/MultiDropdownSelect.tsx:50` | color | TRUE | hardcoded design value |
| 16 | `apps/web/components/phone-input/PhoneInput.tsx:151` | spacing | TRUE | hardcoded design value |
| 17 | `apps/web/modules/onboarding/components/plan-icon.tsx:34` | color | FALSE | `var(--cal-bg, #fff)` fallback; the declaration reads a token |
| 18 | `apps/web/modules/signup-view.tsx:807` | tw_spacing | TRUE | hardcoded design value |
| 19 | `apps/web/modules/event-types/components/tabs/advanced/FormBuilder.tsx:232` | tw_spacing | TRUE | hardcoded design value |
| 20 | `apps/web/app/(use-page-wrapper)/settings/(settings-layout)/SettingsLayoutAppDirClient.tsx:438` | tw_spacing | TRUE | hardcoded design value |
| 21 | `apps/web/modules/embed/components/Embed.tsx:1127` | tw_spacing | TRUE | hardcoded design value |
| 22 | `apps/web/modules/embed/components/Embed.tsx:616` | color | TRUE | hardcoded design value |
| 23 | `apps/web/modules/bookings/components/SlotSelectionModalHeader.tsx:109` | tw_spacing | TRUE | hardcoded design value |
| 24 | `apps/web/modules/bookings/components/event-meta/Details.tsx:185` | tw_spacing | TRUE | hardcoded design value |
| 25 | `apps/web/modules/calendars/weeklyview/components/event/Event.tsx:80` | tw_spacing | TRUE | hardcoded design value |
| 26 | `apps/web/modules/event-types/components/tabs/advanced/CustomEventTypeModal.tsx:333` | tw_spacing | TRUE | hardcoded design value |
| 27 | `apps/web/components/apps/applecalendar/Setup.tsx:28` | tw_spacing | TRUE | hardcoded design value |
| 28 | `apps/web/modules/booking-audit/components/BookingHistory.tsx:352` | tw_spacing | TRUE | hardcoded design value |
| 29 | `apps/web/components/apps/sendgrid/Setup.tsx:41` | tw_spacing | TRUE | hardcoded design value |
| 30 | `apps/web/modules/onboarding/components/onboarding-continuation-prompt.tsx:67` | tw_spacing | TRUE | hardcoded design value |
| 31 | `apps/web/pages/_document.tsx:75` | color | TRUE | hardcoded design value |
| 32 | `apps/web/styles/globals.css:351` | css_duration | TRUE | hardcoded design value |
| 33 | `apps/web/modules/calendars/weeklyview/components/event/Event.tsx:126` | duration | TRUE | hardcoded design value |
| 34 | `apps/web/modules/settings/my-account/components/MailIcon.tsx:36` | color | FALSE | custom-property definition in an embedded `<style>` |
| 35 | `apps/web/modules/event-types/components/MultiDropdownSelect.tsx:30` | tw_spacing | TRUE | hardcoded design value |
| 36 | `apps/web/modules/getting-started/[[...step]]/onboarding-view.tsx:153` | color | FALSE | Tailwind arbitrary custom-property definition `[--cal-brand:#111827]` |
| 37 | `apps/web/modules/event-types/components/tabs/advanced/FormBuilder.tsx:172` | tw_spacing | TRUE | hardcoded design value |
| 38 | `apps/web/modules/event-types/components/tabs/advanced/EventAdvancedTab.tsx:1410` | color | TRUE | hardcoded design value |
| 39 | `apps/web/components/apps/alby/Setup.tsx:149` | color | TRUE | hardcoded design value |
| 40 | `apps/web/app/(use-page-wrapper)/availability/[schedule]/skeleton.tsx:82` | tw_spacing | TRUE | hardcoded design value |
| 41 | `apps/web/modules/videos/views/videos-single-view.tsx:80` | color | TRUE | hardcoded design value |
| 42 | `apps/web/modules/embed/components/Embed.tsx:579` | spacing | TRUE | hardcoded design value |
| 43 | `apps/web/components/apps/hitpay/Setup.tsx:275` | color | TRUE | hardcoded design value |
| 44 | `apps/web/modules/troubleshooter/components/ConnectedAppsContainer.tsx:13` | tw_border_radius | TRUE | hardcoded design value |
| 45 | `apps/web/modules/form-builder/components/Components.tsx:455` | tw_spacing | TRUE | hardcoded design value |
| 46 | `apps/web/components/apps/btcpayserver/Setup.tsx:252` | tw_spacing | TRUE | hardcoded design value |
| 47 | `apps/web/modules/embed/components/Embed.tsx:523` | spacing | TRUE | hardcoded design value |
| 48 | `apps/web/modules/videos/views/videos-single-view.tsx:81` | color | TRUE | hardcoded design value |
| 49 | `apps/web/modules/onboarding/components/plan-icon.tsx:112` | tw_spacing | TRUE | hardcoded design value |
| 50 | `apps/web/modules/onboarding/components/OnboardingLayout.tsx:36` | tw_spacing | TRUE | hardcoded design value |
| 51 | `apps/web/modules/onboarding/store/onboarding-store.ts:127` | color | FALSE | default brand-colour value in app state (user data) |
| 52 | `apps/web/components/apps/exchange2013calendar/Setup.tsx:27` | tw_spacing | TRUE | hardcoded design value |
| 53 | `apps/web/modules/embed/components/Embed.tsx:459` | tw_spacing | TRUE | hardcoded design value |
| 54 | `apps/web/components/settings/CustomEmailTextField.tsx:47` | tw_border_radius | TRUE | hardcoded design value |
| 55 | `apps/web/modules/embed/components/Embed.tsx:578` | spacing | TRUE | hardcoded design value |
| 56 | `apps/web/styles/globals.css:207` | css_spacing | TRUE | hardcoded design value |
| 57 | `apps/web/components/apps/AppPage.tsx:320` | tw_spacing | TRUE | hardcoded design value |
| 58 | `apps/web/components/apps/installation/EventTypesStepCard.tsx:70` | tw_spacing | TRUE | hardcoded design value |
| 59 | `apps/web/modules/signup-view.tsx:383` | tw_border_radius | TRUE | hardcoded design value |
| 60 | `apps/web/components/phone-input/PhoneInput.tsx:98` | spacing | TRUE | hardcoded design value |

_Last updated: 2026-10-08_
