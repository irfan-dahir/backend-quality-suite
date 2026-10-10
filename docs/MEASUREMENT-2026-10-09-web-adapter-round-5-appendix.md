# Appendix — `web` adapter, round 5 held-out corpus, 2026-10-09

Companion to [MEASUREMENT-2026-10-09-web-adapter-round-5.md](./MEASUREMENT-2026-10-09-web-adapter-round-5.md). Sample: `random.Random(20261009).sample(findings, 60)` over findings sorted by (file, line); every finding when fewer than 60. TRUE = real hardcoded design value; FALSE = not a styling value (reason given). Two findings on the same line are separate rows (different literals).

## koel

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `resources/assets/js/components/playable/media-browser/MediaListViewSkeleton.vue:3` | tw_spacing | TRUE | hardcoded styling value |
| 2 | `resources/assets/js/components/ui/form/Btn.vue:49` | css_color | TRUE | hardcoded styling value |
| 3 | `resources/assets/js/components/layout/app-footer/index.vue:225` | css_spacing | TRUE | hardcoded styling value |
| 4 | `resources/assets/js/components/screens/settings/ServicesSettingGroup.vue:66` | color | TRUE | hardcoded styling value |
| 5 | `resources/assets/js/components/koel-plus/KoelPlusModal.vue:5` | tw_spacing | TRUE | hardcoded styling value |
| 6 | `resources/assets/js/components/playable/PlayableThumbnail.vue:5` | tw_spacing | TRUE | hardcoded styling value |
| 7 | `resources/assets/js/remote/components/VolumeControl.vue:69` | css_border_radius | TRUE | hardcoded styling value |
| 8 | `resources/assets/js/components/playlist/PlaylistCollaborationModal.vue:53` | css_spacing | TRUE | hardcoded styling value |
| 9 | `resources/assets/js/components/layout/app-footer/AudioPlayer.vue:201` | css_duration | TRUE | hardcoded styling value |
| 10 | `resources/assets/js/components/podcast/PodcastItem.vue:15` | tw_spacing | TRUE | hardcoded styling value |
| 11 | `resources/assets/js/components/profile-preferences/ChangePasswordForm.vue:37` | tw_spacing | TRUE | hardcoded styling value |
| 12 | `resources/assets/js/components/screens/settings/ServicesSettingGroup.vue:95` | color | TRUE | hardcoded styling value |
| 13 | `resources/assets/js/components/screens/PlaylistScreen.vue:292` | css_spacing | TRUE | hardcoded styling value |
| 14 | `resources/assets/js/remote/components/VolumeControl.vue:72` | css_spacing | TRUE | hardcoded styling value |
| 15 | `resources/assets/js/components/ui/SegmentedControl.vue:18` | tw_spacing | TRUE | hardcoded styling value |
| 16 | `resources/assets/js/components/ui/SoundBars.vue:2` | tw_spacing | TRUE | hardcoded styling value |
| 17 | `resources/assets/js/components/ui/form/CheckBox.vue:5` | tw_spacing | TRUE | hardcoded styling value |
| 18 | `resources/assets/js/components/auth/two-factor/OneTimeCodeInput.vue:10` | tw_spacing | TRUE | hardcoded styling value |
| 19 | `resources/assets/js/remote/App.vue:104` | css_spacing | TRUE | hardcoded styling value |
| 20 | `resources/assets/js/components/ui/form/CheckBox.vue:5` | tw_spacing | TRUE | hardcoded styling value |
| 21 | `resources/assets/js/components/ui/VolumeSlider.vue:13` | tw_spacing | TRUE | hardcoded styling value |
| 22 | `resources/assets/js/components/playable/playable-list/PlayableList.vue:428` | css_spacing | TRUE | hardcoded styling value |
| 23 | `resources/assets/js/components/ui/equalizer/EqualizerBand.vue:99` | css_spacing | TRUE | hardcoded styling value |
| 24 | `resources/assets/js/components/ui/album-artist/AlbumOrArtistInfo.vue:15` | tw_spacing | TRUE | hardcoded styling value |
| 25 | `resources/assets/js/components/playable/EditSongForm.vue:4` | tw_spacing | TRUE | hardcoded styling value |
| 26 | `resources/assets/js/remote/App.vue:103` | css_spacing | TRUE | hardcoded styling value |
| 27 | `resources/assets/js/components/profile-preferences/PreferencesForm.vue:169` | css_spacing | TRUE | hardcoded styling value |
| 28 | `resources/assets/js/components/screens/settings/ServicesSettingGroup.vue:84` | color | TRUE | hardcoded styling value |
| 29 | `resources/assets/js/stores/themeStore.ts:21` | color | FALSE | runtime custom-property definition (`setProperty('--color-highlight-fg', …)`), a token definition |
| 30 | `resources/assets/js/components/ui/FooterPlayButton.vue:4` | tw_spacing | TRUE | hardcoded styling value |
| 31 | `resources/assets/js/components/ui/AppleMusicButton.vue:35` | css_color | TRUE | hardcoded styling value |
| 32 | `resources/assets/js/components/playable/EditSongForm.vue:2` | tw_spacing | TRUE | hardcoded styling value |
| 33 | `resources/assets/js/components/ui/youtube/YouTubeVideoItem.vue:12` | tw_spacing | TRUE | hardcoded styling value |
| 34 | `resources/assets/js/components/ui/VolumeSlider.vue:90` | css_spacing | TRUE | hardcoded styling value |
| 35 | `resources/assets/js/components/layout/app-footer/AudioPlayer.vue:161` | css_spacing | TRUE | hardcoded styling value |
| 36 | `resources/assets/js/components/playable/playable-list/PlayableListItem.vue:66` | tw_spacing | TRUE | hardcoded styling value |
| 37 | `resources/assets/js/components/ui/form/FormRow.vue:11` | tw_spacing | TRUE | hardcoded styling value |
| 38 | `resources/assets/js/remote/components/VolumeControl.vue:81` | css_spacing | TRUE | hardcoded styling value |
| 39 | `resources/assets/js/components/ui/Carousel.vue:120` | css_spacing | TRUE | hardcoded styling value |
| 40 | `resources/assets/js/components/ui/album-artist/ArtistAlbumCardSkeleton.vue:6` | tw_spacing | TRUE | hardcoded styling value |
| 41 | `resources/assets/js/remote/components/VolumeControl.vue:62` | css_spacing | TRUE | hardcoded styling value |
| 42 | `resources/assets/js/components/ui/VolumeSlider.vue:94` | css_duration | TRUE | hardcoded styling value |
| 43 | `resources/assets/js/components/layout/app-footer/index.vue:191` | css_color | TRUE | hardcoded styling value |
| 44 | `resources/assets/js/components/layout/app-footer/AudioPlayer.vue:207` | css_color | TRUE | hardcoded styling value |
| 45 | `resources/assets/js/components/ui/VolumeSlider.vue:89` | css_spacing | TRUE | hardcoded styling value |
| 46 | `resources/assets/js/components/artist/ArtistRow.vue:3` | tw_spacing | TRUE | hardcoded styling value |
| 47 | `resources/assets/js/components/ui/album-artist/AlbumOrArtistCardThumbnail.vue:49` | tw_spacing | TRUE | hardcoded styling value |
| 48 | `resources/assets/js/config/themes.ts:92` | color | FALSE | theme preset record (`thumbnail_color` beside its `--color-*` definitions) |
| 49 | `resources/assets/js/config/themes.ts:65` | color | FALSE | theme preset record (`thumbnail_color` beside its `--color-*` definitions) |
| 50 | `resources/assets/js/components/auth/ResetPasswordForm.vue:4` | tw_spacing | TRUE | hardcoded styling value |
| 51 | `resources/assets/js/config/themes.ts:132` | color | FALSE | theme preset record (`thumbnail_color` beside its `--color-*` definitions) |
| 52 | `resources/assets/js/components/ui/AppleMusicButton.vue:35` | css_color | TRUE | hardcoded styling value |
| 53 | `resources/assets/js/components/ui/Popover.vue:2` | css_spacing | FALSE | off-screen initial position (`left/top: -9999px`); `position` comes from the Tailwind `fixed` class, which the hide-hack rule cannot see |
| 54 | `resources/assets/js/components/profile-preferences/theme/ThemeCard.vue:4` | tw_spacing | TRUE | hardcoded styling value |
| 55 | `resources/assets/js/components/meta/AboutKoelModal.vue:105` | css_color | TRUE | hardcoded styling value |
| 56 | `resources/assets/js/components/screens/UserListScreen.vue:31` | tw_spacing | TRUE | hardcoded styling value |
| 57 | `resources/assets/js/remote/components/VolumeControl.vue:77` | css_border_radius | TRUE | hardcoded styling value |
| 58 | `resources/assets/js/components/artist/ArtistTableRowSkeleton.vue:2` | tw_spacing | TRUE | hardcoded styling value |
| 59 | `resources/assets/js/components/album/AlbumRow.vue:3` | tw_spacing | TRUE | hardcoded styling value |
| 60 | `resources/assets/js/components/ui/ScreenHeader.vue:82` | css_spacing | TRUE | hardcoded styling value |

## jitsi-meet

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `react/features/toolbox/components/web/Toolbox.tsx:62` | spacing | TRUE | hardcoded styling value |
| 2 | `react/features/chat/components/web/ChatMessage.tsx:86` | border_radius | TRUE | hardcoded styling value |
| 3 | `react/features/participants-pane/components/web/RaisedHandIndicator.tsx:13` | spacing | TRUE | hardcoded styling value |
| 4 | `react/features/base/ui/components/web/Switch.tsx:69` | spacing | TRUE | hardcoded styling value |
| 5 | `react/features/gifs/components/web/GifsMenu.tsx:71` | spacing | TRUE | hardcoded styling value |
| 6 | `react/features/base/ui/components/web/Checkbox.tsx:99` | duration | TRUE | hardcoded styling value |
| 7 | `react/features/chat/components/web/ChatInput.tsx:33` | duration | TRUE | hardcoded styling value |
| 8 | `react/features/toolbox/components/web/JitsiPortal.tsx:27` | border_radius | TRUE | hardcoded styling value |
| 9 | `react/features/subtitles/components/web/LanguageListItem.tsx:43` | spacing | TRUE | hardcoded styling value |
| 10 | `react/features/recording/components/LiveStream/native/styles.ts:91` | spacing | TRUE | hardcoded styling value |
| 11 | `react/features/conference/components/native/carmode/styles.ts:110` | spacing | TRUE | hardcoded styling value |
| 12 | `react/features/base/ui/components/web/ClickableIcon.tsx:18` | spacing | TRUE | hardcoded styling value |
| 13 | `react/features/video-menu/components/web/LocalVideoMenuTriggerButton.tsx:124` | spacing | TRUE | hardcoded styling value |
| 14 | `react/features/toolbox/components/web/Toolbox.tsx:61` | spacing | TRUE | hardcoded styling value |
| 15 | `react/features/deep-linking/components/DeepLinkingDesktopPage.web.tsx:38` | spacing | TRUE | hardcoded styling value |
| 16 | `react/features/deep-linking/components/DeepLinkingDesktopPage.web.tsx:44` | spacing | TRUE | hardcoded styling value |
| 17 | `react/features/invite/components/add-people-dialog/native/styles.ts:58` | spacing | TRUE | hardcoded styling value |
| 18 | `react/features/filmstrip/components/native/styles.ts:15` | spacing | TRUE | hardcoded styling value |
| 19 | `react/features/recording/components/LiveStream/native/styles.ts:136` | spacing | TRUE | hardcoded styling value |
| 20 | `react/features/multi-screen/components/SecondScreenStage.web.tsx:77` | spacing | TRUE | hardcoded styling value |
| 21 | `react/features/multi-screen/components/SecondScreenStage.web.tsx:98` | spacing | TRUE | hardcoded styling value |
| 22 | `react/features/polls/components/native/styles.ts:39` | spacing | TRUE | hardcoded styling value |
| 23 | `react/features/speaker-stats/components/web/SpeakerStatsSearch.tsx:27` | spacing | TRUE | hardcoded styling value |
| 24 | `react/features/base/react/components/native/headerstyles.ts:27` | spacing | TRUE | hardcoded styling value |
| 25 | `react/features/reactions/components/web/ReactionsMenu.tsx:96` | spacing | TRUE | hardcoded styling value |
| 26 | `react/features/participants-pane/components/web/VisitorsList.tsx:47` | spacing | TRUE | hardcoded styling value |
| 27 | `react/features/multi-screen/components/SecondScreenTile.web.tsx:63` | border_radius | TRUE | hardcoded styling value |
| 28 | `react/features/chat/components/web/ChatMessage.tsx:147` | spacing | TRUE | hardcoded styling value |
| 29 | `react/features/participants-pane/components/web/LobbyParticipantItem.tsx:50` | spacing | TRUE | hardcoded styling value |
| 30 | `react/features/notifications/components/web/NotificationsContainer.tsx:50` | spacing | TRUE | hardcoded styling value |
| 31 | `react/features/chat/components/web/ChatInput.tsx:31` | spacing | TRUE | hardcoded styling value |
| 32 | `react/features/salesforce/components/native/styles.ts:147` | spacing | TRUE | hardcoded styling value |
| 33 | `react/features/prejoin/components/web/preview/DeviceStatus.tsx:42` | spacing | TRUE | hardcoded styling value |
| 34 | `react/features/deep-linking/components/DeepLinkingMobilePage.web.tsx:53` | spacing | TRUE | hardcoded styling value |
| 35 | `react/features/toolbox/components/native/styles.ts:30` | spacing | TRUE | hardcoded styling value |
| 36 | `react/features/invite/components/add-people-dialog/native/styles.ts:49` | spacing | TRUE | hardcoded styling value |
| 37 | `react/features/recording/components/Recording/styles.web.ts:193` | spacing | TRUE | hardcoded styling value |
| 38 | `react/features/participants-pane/components/web/VisitorsItem.tsx:28` | spacing | TRUE | hardcoded styling value |
| 39 | `react/features/invite/components/dial-in-summary/web/DialInSummary.tsx:96` | color | TRUE | hardcoded styling value |
| 40 | `react/features/invite/components/add-people-dialog/native/styles.ts:62` | spacing | TRUE | hardcoded styling value |
| 41 | `react/features/chat/components/native/styles.ts:442` | spacing | TRUE | hardcoded styling value |
| 42 | `react/features/polls/components/web/PollCreate.tsx:29` | spacing | TRUE | hardcoded styling value |
| 43 | `react/features/multi-screen/components/SecondScreenTile.web.tsx:90` | spacing | TRUE | hardcoded styling value |
| 44 | `react/features/base/ui/components/web/Checkbox.tsx:137` | spacing | TRUE | hardcoded styling value |
| 45 | `react/features/chat/components/web/MessageRecipient.tsx:19` | spacing | TRUE | hardcoded styling value |
| 46 | `react/features/polls/components/native/styles.ts:71` | spacing | TRUE | hardcoded styling value |
| 47 | `react/features/recording/components/Recording/styles.web.ts:30` | border_radius | TRUE | hardcoded styling value |
| 48 | `react/features/salesforce/components/web/PendingSection.tsx:86` | spacing | TRUE | hardcoded styling value |
| 49 | `react/features/toolbox/components/web/AudioMuteButton.tsx:24` | spacing | TRUE | hardcoded styling value |
| 50 | `react/features/invite/components/callee-info/styles.native.ts:26` | spacing | TRUE | hardcoded styling value |
| 51 | `react/features/participants-pane/components/breakout-rooms/components/web/CollapsibleRoom.tsx:104` | spacing | TRUE | hardcoded styling value |
| 52 | `react/features/recent-list/components/styles.native.ts:42` | spacing | TRUE | hardcoded styling value |
| 53 | `react/features/multi-screen/components/SecondScreenStage.web.tsx:87` | spacing | TRUE | hardcoded styling value |
| 54 | `react/features/speaker-stats/components/web/SpeakerStats.tsx:113` | border_radius | TRUE | hardcoded styling value |
| 55 | `react/features/base/ui/components/web/Checkbox.tsx:144` | spacing | TRUE | hardcoded styling value |
| 56 | `react/features/multi-screen/components/SecondScreenWhiteboard.web.tsx:34` | color | TRUE | hardcoded styling value |
| 57 | `react/features/base/ui/components/web/Select.tsx:123` | spacing | TRUE | hardcoded styling value |
| 58 | `react/features/base/ui/components/web/ContextMenu.tsx:165` | spacing | TRUE | hardcoded styling value |
| 59 | `react/features/multi-screen/components/SecondScreenTile.web.tsx:85` | border_radius | TRUE | hardcoded styling value |
| 60 | `react/features/settings/components/web/audio/SpeakerEntry.tsx:80` | spacing | TRUE | hardcoded styling value |

## pocketbase

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `ui/src/css/dropdown.css:64` | css_spacing | TRUE | hardcoded styling value |
| 2 | `ui/src/css/recordSummary.css:63` | css_spacing | TRUE | hardcoded styling value |
| 3 | `ui/src/css/base.css:1076` | css_spacing | TRUE | hardcoded styling value |
| 4 | `ui/src/css/layout.css:211` | css_spacing | TRUE | hardcoded styling value |
| 5 | `ui/src/css/base.css:696` | css_spacing | TRUE | hardcoded styling value |
| 6 | `ui/src/css/colorPicker.css:91` | css_spacing | TRUE | hardcoded styling value |
| 7 | `ui/src/css/export.css:116` | css_spacing | TRUE | hardcoded styling value |
| 8 | `ui/src/css/base.css:778` | css_spacing | TRUE | hardcoded styling value |
| 9 | `ui/src/css/form.css:495` | css_spacing | TRUE | hardcoded styling value |
| 10 | `ui/src/css/form.css:567` | css_spacing | TRUE | hardcoded styling value |
| 11 | `ui/src/css/layout.css:363` | css_spacing | TRUE | hardcoded styling value |
| 12 | `ui/src/css/form.css:964` | css_spacing | TRUE | hardcoded styling value |
| 13 | `ui/src/css/logs.css:207` | css_spacing | TRUE | hardcoded styling value |
| 14 | `ui/src/css/map.css:7` | css_spacing | TRUE | hardcoded styling value |
| 15 | `ui/src/css/sqlConsole.css:4` | css_spacing | TRUE | hardcoded styling value |
| 16 | `ui/src/css/base.css:151` | css_spacing | TRUE | hardcoded styling value |
| 17 | `ui/src/css/ruleField.css:5` | css_spacing | TRUE | hardcoded styling value |
| 18 | `ui/src/css/modal.css:214` | css_spacing | TRUE | hardcoded styling value |
| 19 | `ui/src/css/dropdown.css:135` | css_spacing | TRUE | hardcoded styling value |
| 20 | `ui/src/css/recordFilePicker.css:3` | css_spacing | TRUE | hardcoded styling value |
| 21 | `ui/src/css/recordFields.css:120` | css_spacing | TRUE | hardcoded styling value |
| 22 | `ui/src/css/colorPicker.css:85` | css_spacing | TRUE | hardcoded styling value |
| 23 | `ui/src/css/form.css:684` | css_spacing | TRUE | hardcoded styling value |
| 24 | `ui/src/css/layout.css:277` | css_spacing | TRUE | hardcoded styling value |
| 25 | `ui/src/css/recordsPicker.css:2` | css_spacing | TRUE | hardcoded styling value |
| 26 | `ui/src/css/list.css:32` | css_spacing | TRUE | hardcoded styling value |
| 27 | `ui/src/css/layout.css:366` | css_spacing | TRUE | hardcoded styling value |
| 28 | `ui/src/css/colorPicker.css:64` | css_spacing | TRUE | hardcoded styling value |
| 29 | `ui/src/css/table.css:115` | css_spacing | TRUE | hardcoded styling value |
| 30 | `ui/src/css/providers.css:41` | css_spacing | TRUE | hardcoded styling value |
| 31 | `ui/src/css/base.css:720` | css_spacing | TRUE | hardcoded styling value |
| 32 | `ui/src/css/erd.css:47` | css_spacing | TRUE | hardcoded styling value |
| 33 | `ui/src/css/sqlConsole.css:20` | css_spacing | TRUE | hardcoded styling value |
| 34 | `ui/src/css/layout.css:519` | css_spacing | TRUE | hardcoded styling value |
| 35 | `ui/src/css/recordFields.css:121` | css_spacing | TRUE | hardcoded styling value |
| 36 | `ui/src/css/logs.css:235` | css_spacing | TRUE | hardcoded styling value |
| 37 | `ui/src/css/base.css:775` | css_spacing | TRUE | hardcoded styling value |
| 38 | `ui/src/css/ratelimit.css:13` | css_spacing | TRUE | hardcoded styling value |
| 39 | `ui/src/css/base.css:897` | css_spacing | TRUE | hardcoded styling value |
| 40 | `ui/src/css/base.css:787` | css_spacing | TRUE | hardcoded styling value |
| 41 | `ui/src/css/prism.css:18` | css_spacing | TRUE | hardcoded styling value |
| 42 | `ui/src/css/accordion.css:46` | css_spacing | TRUE | hardcoded styling value |
| 43 | `ui/src/css/recordFields.css:76` | css_spacing | TRUE | hardcoded styling value |
| 44 | `ui/src/css/tabs.css:6` | css_spacing | TRUE | hardcoded styling value |
| 45 | `ui/src/css/table.css:210` | css_spacing | TRUE | hardcoded styling value |
| 46 | `ui/src/css/apiPreviewModal.css:102` | css_spacing | TRUE | hardcoded styling value |
| 47 | `ui/src/css/toast.css:51` | css_spacing | TRUE | hardcoded styling value |
| 48 | `ui/src/css/layout.css:402` | css_spacing | TRUE | hardcoded styling value |
| 49 | `ui/src/css/list.css:82` | css_spacing | TRUE | hardcoded styling value |
| 50 | `ui/src/css/base.css:693` | css_spacing | TRUE | hardcoded styling value |
| 51 | `ui/src/css/form.css:837` | css_spacing | TRUE | hardcoded styling value |
| 52 | `ui/src/css/collectionsOverview.css:36` | css_spacing | TRUE | hardcoded styling value |
| 53 | `ui/src/css/layout.css:57` | css_spacing | TRUE | hardcoded styling value |
| 54 | `ui/src/css/apiPreviewModal.css:6` | css_spacing | TRUE | hardcoded styling value |
| 55 | `ui/src/base/erd.js:32` | spacing | TRUE | hardcoded styling value |
| 56 | `ui/src/css/logs.css:133` | css_spacing | TRUE | hardcoded styling value |
| 57 | `ui/src/css/layout.css:210` | css_spacing | TRUE | hardcoded styling value |
| 58 | `ui/src/css/base.css:802` | css_spacing | TRUE | hardcoded styling value |
| 59 | `ui/src/css/dropdown.css:65` | css_spacing | TRUE | hardcoded styling value |
| 60 | `ui/src/css/form.css:925` | css_spacing | TRUE | hardcoded styling value |

## n8n

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ResourceLocator/ResourceLocatorDropdown.vue:428` | css_border_radius | TRUE | hardcoded styling value |
| 2 | `packages/frontend/editor-ui/src/features/shared/nodeCreator/components/ItemTypes/ActionItem.vue:143` | css_spacing | TRUE | hardcoded styling value |
| 3 | `packages/frontend/editor-ui/src/experiments/readyToRunWorkflows/workflows/1_playground.ts:129` | spacing | FALSE | workflow-definition data: sticky-note node geometry in a seed workflow (`experiments/readyToRunWorkflows/workflows/`) |
| 4 | `packages/frontend/editor-ui/src/features/workflows/canvas/components/elements/nodes/render-types/_canvasNodeStyles.scss:79` | css_duration | TRUE | hardcoded styling value |
| 5 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/components/shared/VersionAvatar.vue:59` | css_spacing | TRUE | hardcoded styling value |
| 6 | `packages/frontend/editor-ui/src/experiments/instanceAiWorkflowPreviewSuggestions/components/WorkflowPreviewNode.vue:84` | css_spacing | TRUE | hardcoded styling value |
| 7 | `packages/frontend/editor-ui/src/features/agents/components/AgentSkillViewer.vue:578` | css_spacing | TRUE | hardcoded styling value |
| 8 | `packages/frontend/editor-ui/src/app/dev/dev-panel/DevPanel.vue:938` | css_border_radius | TRUE | hardcoded styling value |
| 9 | `packages/frontend/editor-ui/src/experiments/openWorkflowInAssistant/components/OpenWorkflowInAssistantNotification.vue:91` | css_color | TRUE | hardcoded styling value |
| 10 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ParameterInputList.vue:1081` | css_duration | TRUE | hardcoded styling value |
| 11 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/MultipleParameter.vue:217` | css_color | TRUE | hardcoded styling value |
| 12 | `packages/frontend/editor-ui/src/features/core/auth/views/ConfirmEmailChangeView.vue:119` | css_color | TRUE | hardcoded styling value |
| 13 | `packages/frontend/editor-ui/src/features/workflows/canvas/components/elements/handles/render-types/parts/CanvasHandleDiamond.vue:21` | css_spacing | TRUE | hardcoded styling value |
| 14 | `packages/frontend/editor-ui/src/features/workflows/templates/views/TemplatesWorkflowView.vue:243` | css_spacing | TRUE | hardcoded styling value |
| 15 | `packages/frontend/editor-ui/src/features/shared/nodeCreator/components/Panel/SearchBar.vue:82` | css_spacing | TRUE | hardcoded styling value |
| 16 | `packages/frontend/editor-ui/src/experiments/readyToRunWorkflows/workflows/4_playground.ts:212` | spacing | FALSE | workflow-definition data: sticky-note node geometry in a seed workflow (`experiments/readyToRunWorkflows/workflows/`) |
| 17 | `packages/frontend/editor-ui/src/app/views/LoadingView.vue:31` | css_spacing | TRUE | hardcoded styling value |
| 18 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/components/shared/VersionAvatar.vue:64` | css_spacing | TRUE | hardcoded styling value |
| 19 | `packages/frontend/editor-ui/src/features/ndv/runData/components/BinaryEntryDataTable.vue:196` | css_duration | TRUE | hardcoded styling value |
| 20 | `packages/frontend/editor-ui/src/features/shared/nodeCreator/components/Panel/NodesListPanel.vue:430` | css_spacing | TRUE | hardcoded styling value |
| 21 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ResourceLocator/ResourceLocatorDropdown.vue:424` | css_spacing | TRUE | hardcoded styling value |
| 22 | `packages/frontend/editor-ui/src/experiments/resourceCenter/components/ResourceFeatureCard.vue:313` | css_spacing | TRUE | hardcoded styling value |
| 23 | `packages/frontend/editor-ui/src/experiments/resourceCenter/components/ResourceFeatureCard.vue:329` | css_spacing | TRUE | hardcoded styling value |
| 24 | `packages/frontend/editor-ui/src/features/agents/components/AgentsListIntro.vue:98` | css_spacing | TRUE | hardcoded styling value |
| 25 | `packages/frontend/editor-ui/src/features/agents/agentTemplates.ts:148` | color | TRUE | hardcoded styling value |
| 26 | `packages/frontend/editor-ui/src/features/core/dataTable/DataTableDetailsView.vue:283` | css_spacing | TRUE | hardcoded styling value |
| 27 | `packages/frontend/editor-ui/src/features/ai/chatHub/components/CanvasChatHubPanel.vue:524` | css_spacing | TRUE | hardcoded styling value |
| 28 | `packages/frontend/editor-ui/src/features/ai/chatHub/components/CanvasChatSessionDropdown.vue:224` | css_spacing | TRUE | hardcoded styling value |
| 29 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/views/EvaluationsView.vue:347` | css_border_radius | TRUE | hardcoded styling value |
| 30 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ExpressionParameterInput.vue:296` | css_spacing | TRUE | hardcoded styling value |
| 31 | `packages/frontend/editor-ui/src/app/components/UpdatesPanel.vue:99` | css_spacing | TRUE | hardcoded styling value |
| 32 | `packages/frontend/editor-ui/src/features/workflows/workflowDiff/workflowDiff.module.scss:12` | css_spacing | TRUE | hardcoded styling value |
| 33 | `packages/frontend/editor-ui/src/features/collaboration/projects/components/ProjectIcon.vue:90` | css_spacing | TRUE | hardcoded styling value |
| 34 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/views/CompareCollectionView.vue:247` | css_spacing | TRUE | hardcoded styling value |
| 35 | `packages/frontend/editor-ui/src/features/ai/chatHub/components/ChatGreetings.vue:124` | css_spacing | TRUE | hardcoded styling value |
| 36 | `packages/frontend/editor-ui/src/experiments/readyToRunWorkflows/workflows/1_playground.ts:155` | spacing | FALSE | workflow-definition data: sticky-note node geometry in a seed workflow (`experiments/readyToRunWorkflows/workflows/`) |
| 37 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/components/Tests/ExecutionRow.vue:195` | css_spacing | TRUE | hardcoded styling value |
| 38 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/components/Compare/MetricsTab.vue:88` | css_spacing | TRUE | hardcoded styling value |
| 39 | `packages/frontend/editor-ui/src/experiments/instanceAiWorkflowPreviewSuggestions/components/visualizations/TelegramChatVisualization.vue:370` | css_color | TRUE | hardcoded styling value |
| 40 | `packages/frontend/editor-ui/src/features/execution/logs/components/LogsOverviewRow.vue:358` | css_spacing | TRUE | hardcoded styling value |
| 41 | `packages/frontend/editor-ui/src/features/ai/shared/styles/_question-option-rows.scss:32` | css_duration | TRUE | hardcoded styling value |
| 42 | `packages/frontend/editor-ui/src/features/workflows/components/WorkflowSettings/WorkflowSettings.vue:1847` | css_duration | TRUE | hardcoded styling value |
| 43 | `packages/frontend/editor-ui/src/experiments/surfaceMcpToNewCloudUsers/components/SurfaceMcpBridgeGraphic.vue:205` | css_spacing | TRUE | hardcoded styling value |
| 44 | `packages/frontend/editor-ui/src/features/workflows/canvas/components/Canvas.vue:2271` | css_duration | TRUE | hardcoded styling value |
| 45 | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ParameterInput.vue:2341` | css_spacing | TRUE | hardcoded styling value |
| 46 | `packages/frontend/editor-ui/src/features/settings/sso/provisioning/components/DefaultConditionRow.vue:66` | css_spacing | TRUE | hardcoded styling value |
| 47 | `packages/frontend/editor-ui/src/features/agents/components/AgentTypingIndicator.vue:23` | css_duration | TRUE | hardcoded styling value |
| 48 | `packages/frontend/editor-ui/src/features/workflows/templates/components/TemplatesInfoCarousel.vue:159` | css_spacing | TRUE | hardcoded styling value |
| 49 | `packages/frontend/editor-ui/src/features/execution/executions/components/ExecutionsFilter.vue:597` | css_spacing | TRUE | hardcoded styling value |
| 50 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/components/shared/VersionAvatar.vue:75` | css_spacing | TRUE | hardcoded styling value |
| 51 | `packages/frontend/editor-ui/src/features/ai/assistant/components/Agent/PlanQuestionsMessage.vue:758` | css_duration | TRUE | hardcoded styling value |
| 52 | `packages/frontend/editor-ui/src/features/agents/components/EvalInitialSample.vue:78` | css_spacing | TRUE | hardcoded styling value |
| 53 | `packages/frontend/editor-ui/src/experiments/instanceAiWorkflowPreviewSuggestions/components/visualizations/TelegramChatVisualization.vue:365` | css_spacing | TRUE | hardcoded styling value |
| 54 | `packages/frontend/editor-ui/src/features/ai/instanceAi/components/AgentBuildingIndicator.vue:245` | css_color | TRUE | hardcoded styling value |
| 55 | `packages/frontend/editor-ui/src/features/ai/chatHub/components/ChatSidebarContent.vue:287` | css_spacing | TRUE | hardcoded styling value |
| 56 | `packages/frontend/editor-ui/src/features/workflows/canvas/components/elements/handles/render-types/CanvasHandleMainOutput.vue:116` | css_spacing | TRUE | hardcoded styling value |
| 57 | `packages/frontend/editor-ui/src/app/views/CanvasAddButton.vue:68` | css_spacing | TRUE | hardcoded styling value |
| 58 | `packages/frontend/editor-ui/src/features/settings/orchestration.ee/components/WorkerCard.vue:136` | css_spacing | TRUE | hardcoded styling value |
| 59 | `packages/frontend/editor-ui/src/experiments/readyToRunWorkflows/workflows/2_playground.ts:311` | color | FALSE | user-content CSS string (`customCss`) inside a seed workflow's form-node options |
| 60 | `packages/frontend/editor-ui/src/features/ai/evaluation.ee/views/EvaluationsView.vue:428` | css_spacing | TRUE | hardcoded styling value |

## plausible/analytics

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `assets/js/app.js:86` | spacing | TRUE | hardcoded styling value |
| 2 | `assets/js/app.js:86` | spacing | TRUE | hardcoded styling value |
| 3 | `assets/js/app.js:118` | spacing | TRUE | hardcoded styling value |
| 4 | `assets/js/app.js:118` | spacing | TRUE | hardcoded styling value |
| 5 | `assets/js/app.js:119` | color | TRUE | hardcoded styling value |
| 6 | `assets/js/dashboard/annotations/annotation-list-items.tsx:16` | tw_spacing | TRUE | hardcoded styling value |
| 7 | `assets/js/dashboard/components/feature-setup-notice.tsx:94` | tw_spacing | TRUE | hardcoded styling value |
| 8 | `assets/js/dashboard/components/form-elements.tsx:202` | tw_spacing | TRUE | hardcoded styling value |
| 9 | `assets/js/dashboard/components/tabs.tsx:38` | tw_spacing | TRUE | hardcoded styling value |
| 10 | `assets/js/dashboard/components/tabs.tsx:65` | tw_spacing | TRUE | hardcoded styling value |
| 11 | `assets/js/dashboard/components/tabs.tsx:101` | tw_spacing | TRUE | hardcoded styling value |
| 12 | `assets/js/dashboard/components/tabs.tsx:190` | tw_spacing | TRUE | hardcoded styling value |
| 13 | `assets/js/dashboard/extra/exploration/exploration-column.tsx:290` | tw_spacing | TRUE | hardcoded styling value |
| 14 | `assets/js/dashboard/extra/exploration/exploration-column.tsx:391` | tw_spacing | TRUE | hardcoded styling value |
| 15 | `assets/js/dashboard/nav-menu/filter-pill.tsx:59` | spacing | FALSE | popper.js `preventOverflow` modifier `padding: 8` — a positioning-engine parameter, not a CSS declaration |
| 16 | `assets/js/dashboard/nav-menu/submenu.tsx:83` | spacing | FALSE | popper.js `preventOverflow` modifier `padding: 8` — a positioning-engine parameter, not a CSS declaration |
| 17 | `assets/js/dashboard/stats/graph/main-graph.tsx:650` | tw_spacing | TRUE | hardcoded styling value |
| 18 | `assets/js/dashboard/stats/graph/main-graph.tsx:650` | tw_spacing | TRUE | hardcoded styling value |
| 19 | `assets/js/dashboard/stats/graph/main-graph.tsx:969` | color | TRUE | hardcoded styling value |
| 20 | `assets/js/dashboard/stats/graph/main-graph.tsx:970` | color | TRUE | hardcoded styling value |
| 21 | `assets/js/dashboard/stats/graph/main-graph.tsx:974` | color | TRUE | hardcoded styling value |
| 22 | `assets/js/dashboard/stats/graph/main-graph.tsx:975` | color | TRUE | hardcoded styling value |
| 23 | `assets/js/dashboard/stats/graph/main-graph.tsx:981` | color | TRUE | hardcoded styling value |
| 24 | `assets/js/dashboard/stats/graph/main-graph.tsx:982` | color | TRUE | hardcoded styling value |
| 25 | `assets/js/dashboard/stats/graph/main-graph.tsx:986` | color | TRUE | hardcoded styling value |
| 26 | `assets/js/dashboard/stats/graph/main-graph.tsx:987` | color | TRUE | hardcoded styling value |
| 27 | `assets/js/dashboard/stats/graph/main-graph.tsx:995` | tw_color | TRUE | hardcoded styling value |
| 28 | `assets/js/dashboard/stats/graph/main-graph.tsx:995` | tw_color | TRUE | hardcoded styling value |
| 29 | `assets/js/dashboard/stats/graph/main-graph.tsx:1001` | tw_color | TRUE | hardcoded styling value |
| 30 | `assets/js/dashboard/stats/graph/main-graph.tsx:1001` | tw_color | TRUE | hardcoded styling value |
| 31 | `assets/js/dashboard/stats/graph/top-stats.js:117` | spacing | TRUE | hardcoded styling value |
| 32 | `assets/js/dashboard/stats/graph/top-stats.js:117` | spacing | TRUE | hardcoded styling value |
| 33 | `assets/js/dashboard/stats/graph/top-stats.js:128` | tw_spacing | TRUE | hardcoded styling value |
| 34 | `assets/js/dashboard/stats/graph/top-stats.js:179` | tw_spacing | TRUE | hardcoded styling value |
| 35 | `assets/js/dashboard/stats/graph/top-stats.js:209` | tw_spacing | TRUE | hardcoded styling value |
| 36 | `assets/js/dashboard/stats/locations/world-map-svg.tsx:138` | color | TRUE | hardcoded styling value |
| 37 | `assets/js/dashboard/stats/locations/world-map-svg.tsx:138` | color | TRUE | hardcoded styling value |
| 38 | `assets/js/dashboard/stats/locations/world-map-svg.tsx:139` | color | TRUE | hardcoded styling value |
| 39 | `assets/js/dashboard/stats/locations/world-map-svg.tsx:139` | color | TRUE | hardcoded styling value |
| 40 | `assets/js/dashboard/stats/modals/breakdown-table.tsx:50` | tw_spacing | TRUE | hardcoded styling value |
| 41 | `assets/js/dashboard/stats/more-link.js:33` | tw_spacing | TRUE | hardcoded styling value |
| 42 | `assets/js/dashboard/stats/pages/index.tsx:185` | tw_spacing | TRUE | hardcoded styling value |
| 43 | `assets/js/dashboard/stats/reports/report-layout.tsx:17` | tw_spacing | TRUE | hardcoded styling value |
| 44 | `assets/js/liveview/live_socket.js:80` | color | TRUE | hardcoded styling value |

_Last updated: 2026-10-09_
