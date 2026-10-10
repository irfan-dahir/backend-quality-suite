# Appendix — `web` adapter, round 4 held-out corpus, 2026-10-09

Companion to [MEASUREMENT-2026-10-09-web-adapter-round-4.md](./MEASUREMENT-2026-10-09-web-adapter-round-4.md). Sample: `random.Random(20261009).sample(findings, 60)`. TRUE = real hardcoded design value; FALSE = not a styling value (reason given).

## uptime-kuma

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `src/components/MonitorListItem.vue:339` | css_spacing | TRUE | hardcoded styling value |
| 2 | `src/pages/AddStatusPage.vue:110` | css_spacing | TRUE | hardcoded styling value |
| 3 | `src/components/MonitorList.vue:614` | css_spacing | TRUE | hardcoded styling value |
| 4 | `src/components/notifications/Line.vue:21` | css_spacing | TRUE | hardcoded styling value |
| 5 | `src/components/APIKeyDialog.vue:198` | css_spacing | TRUE | hardcoded styling value |
| 6 | `src/components/MonitorListFilter.vue:374` | css_spacing | TRUE | hardcoded styling value |
| 7 | `src/pages/Settings.vue:250` | css_spacing | TRUE | hardcoded styling value |
| 8 | `src/components/PingChart.vue:604` | css_spacing | TRUE | hardcoded styling value |
| 9 | `src/components/CopyableInput.vue:17` | css_spacing | FALSE | off-screen hide hack (`left: -999999px`), not a scale value |
| 10 | `src/components/Tag.vue:118` | css_spacing | TRUE | hardcoded styling value |
| 11 | `src/components/TagEditDialog.vue:46` | css_spacing | TRUE | hardcoded styling value |
| 12 | `src/components/notifications/Mattermost.vue:59` | css_spacing | TRUE | hardcoded styling value |
| 13 | `src/components/Tooltip.vue:206` | css_color | TRUE | hardcoded styling value |
| 14 | `src/pages/Settings.vue:252` | css_spacing | TRUE | hardcoded styling value |
| 15 | `src/components/settings/APIKeys.vue:182` | css_spacing | TRUE | hardcoded styling value |
| 16 | `src/components/settings/APIKeys.vue:217` | css_spacing | TRUE | hardcoded styling value |
| 17 | `src/pages/Details.vue:887` | css_spacing | TRUE | hardcoded styling value |
| 18 | `src/assets/app.scss:446` | css_duration | TRUE | hardcoded styling value |
| 19 | `src/pages/NotFound.vue:80` | css_spacing | TRUE | hardcoded styling value |
| 20 | `src/pages/DashboardHome.vue:337` | css_spacing | TRUE | hardcoded styling value |
| 21 | `src/components/settings/About.vue:73` | css_spacing | TRUE | hardcoded styling value |
| 22 | `src/components/MonitorListItem.vue:344` | css_spacing | TRUE | hardcoded styling value |
| 23 | `src/layouts/Layout.vue:403` | css_color | TRUE | hardcoded styling value |
| 24 | `src/layouts/Layout.vue:296` | css_spacing | TRUE | hardcoded styling value |
| 25 | `src/components/MonitorListFilter.vue:360` | css_spacing | TRUE | hardcoded styling value |
| 26 | `src/pages/SetupDatabase.vue:301` | css_spacing | TRUE | hardcoded styling value |
| 27 | `src/pages/ManageStatusPage.vue:172` | css_spacing | TRUE | hardcoded styling value |
| 28 | `src/components/TagsManager.vue:117` | css_spacing | TRUE | hardcoded styling value |
| 29 | `src/components/notifications/Mattermost.vue:53` | css_spacing | TRUE | hardcoded styling value |
| 30 | `src/pages/Setup.vue:169` | css_spacing | TRUE | hardcoded styling value |
| 31 | `src/pages/DashboardHome.vue:312` | css_spacing | TRUE | hardcoded styling value |
| 32 | `src/components/notifications/Signal.vue:50` | css_spacing | TRUE | hardcoded styling value |
| 33 | `src/components/notifications/Notifery.vue:34` | css_spacing | TRUE | hardcoded styling value |
| 34 | `src/components/MonitorListFilter.vue:349` | css_spacing | TRUE | hardcoded styling value |
| 35 | `src/pages/Details.vue:962` | css_spacing | TRUE | hardcoded styling value |
| 36 | `src/components/settings/Notifications.vue:282` | css_spacing | TRUE | hardcoded styling value |
| 37 | `src/components/CertificateInfoRow.vue:101` | css_spacing | TRUE | hardcoded styling value |
| 38 | `src/components/PingChart.vue:111` | spacing | TRUE | hardcoded styling value |
| 39 | `src/pages/Details.vue:911` | css_spacing | TRUE | hardcoded styling value |
| 40 | `src/pages/Settings.vue:294` | css_border_radius | TRUE | hardcoded styling value |
| 41 | `src/pages/StatusPage.vue:1542` | css_spacing | TRUE | hardcoded styling value |
| 42 | `src/components/notifications/RocketChat.vue:28` | css_spacing | TRUE | hardcoded styling value |
| 43 | `src/layouts/Layout.vue:302` | css_spacing | TRUE | hardcoded styling value |
| 44 | `src/pages/Settings.vue:245` | css_spacing | TRUE | hardcoded styling value |
| 45 | `src/components/settings/APIKeys.vue:213` | css_spacing | TRUE | hardcoded styling value |
| 46 | `src/pages/StatusPage.vue:1791` | css_spacing | TRUE | hardcoded styling value |
| 47 | `src/components/CopyableInput.vue:17` | css_spacing | FALSE | off-screen hide hack (`top: -999999px`) |
| 48 | `src/components/settings/RemoteBrowsers.vue:8` | css_border_radius | TRUE | hardcoded styling value |
| 49 | `src/components/IncidentHistory.vue:126` | css_border_radius | TRUE | hardcoded styling value |
| 50 | `src/components/EditMonitorConditionGroup.vue:167` | css_color | TRUE | hardcoded styling value |
| 51 | `src/components/settings/Docker.vue:8` | css_border_radius | TRUE | hardcoded styling value |
| 52 | `src/pages/StatusPage.vue:1677` | css_duration | TRUE | hardcoded styling value |
| 53 | `src/assets/app.scss:112` | css_spacing | TRUE | hardcoded styling value |
| 54 | `src/layouts/Layout.vue:283` | css_spacing | TRUE | hardcoded styling value |
| 55 | `src/pages/ManageMaintenance.vue:251` | css_color | TRUE | hardcoded styling value |
| 56 | `src/pages/ManageMaintenance.vue:230` | css_spacing | TRUE | hardcoded styling value |
| 57 | `src/assets/app.scss:259` | css_color | TRUE | hardcoded styling value |
| 58 | `src/pages/ManageMaintenance.vue:304` | css_spacing | TRUE | hardcoded styling value |
| 59 | `src/components/notifications/Onesender.vue:88` | css_spacing | TRUE | hardcoded styling value |
| 60 | `src/pages/Settings.vue:262` | css_border_radius | TRUE | hardcoded styling value |

## AdGuardHome

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `client/src/components/ui/Tabler.css:13564` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 2 | `client/src/components/ui/Tabler.css:15458` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 3 | `client/src/components/ui/Tabler.css:3346` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 4 | `client/src/components/ui/Tabler.css:15837` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 5 | `client/src/components/ui/Tabler.css:10185` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 6 | `client/src/components/ui/Tabler.css:2305` | css_border_radius | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 7 | `client/src/components/ui/Tabler.css:7512` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 8 | `client/src/components/ui/Line.css:14` | css_spacing | TRUE | hardcoded styling value |
| 9 | `client/src/components/ui/Tabler.css:3158` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 10 | `client/src/components/ui/Tabler.css:13517` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 11 | `client/src/components/ui/Tabler.css:13183` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 12 | `client/src/components/ui/Tabler.css:11859` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 13 | `client/src/components/ui/Tabler.css:10181` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 14 | `client/src/components/ui/Tabler.css:15633` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 15 | `client/src/components/ui/Tabler.css:16290` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 16 | `client/src/components/ui/Tabler.css:15499` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 17 | `client/src/components/ui/Tabler.css:4456` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 18 | `client/src/components/ui/Tabler.css:111` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 19 | `client/src/components/ui/Tabler.css:10191` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 20 | `client/src/components/ui/Tabler.css:13850` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 21 | `client/src/components/ui/Tabler.css:15494` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 22 | `client/src/components/ui/Tabler.css:13559` | css_border_radius | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 23 | `client/src/components/ui/Tabler.css:4952` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 24 | `client/src/components/ui/Tabler.css:4984` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 25 | `client/src/components/ui/Tabler.css:7688` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 26 | `client/src/components/ui/Tabler.css:5645` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 27 | `client/src/components/ui/Tabler.css:11895` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 28 | `client/src/components/ui/Tabler.css:8592` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 29 | `client/src/components/ui/Tabler.css:8638` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 30 | `client/src/components/ui/Tabler.css:10412` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 31 | `client/src/components/ui/Tabler.css:13072` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 32 | `client/src/install/Setup/Setup.css:25` | css_spacing | TRUE | hardcoded styling value |
| 33 | `client/src/components/Logs/Logs.css:140` | css_spacing | TRUE | hardcoded styling value |
| 34 | `client/src/components/ui/Tabler.css:16466` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 35 | `client/src/components/ui/Tabler.css:11698` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 36 | `client/src/components/ui/Tabler.css:10286` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 37 | `client/src/components/ui/Tabler.css:8914` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 38 | `client/src/components/ui/Tabler.css:3429` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 39 | `client/src/components/ui/Tabler.css:9902` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 40 | `client/src/components/ui/Tabler.css:9392` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 41 | `client/src/components/ui/Tabler.css:3133` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 42 | `client/src/components/ui/Tabler.css:12309` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 43 | `client/src/components/ui/Tabler.css:11638` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 44 | `client/src/components/ui/Tabler.css:15995` | css_border_radius | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 45 | `client/src/components/ui/Tabler.css:5143` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 46 | `client/src/components/ui/Tabler.css:15613` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 47 | `client/src/components/ui/Tabler.css:13285` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 48 | `client/src/components/ui/Tabler.css:15054` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 49 | `client/src/components/ui/Tabler.css:7640` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 50 | `client/src/components/ui/Tabler.css:16156` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 51 | `client/src/components/ui/Tabler.css:12108` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 52 | `client/src/components/ui/Tabler.css:10201` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 53 | `client/src/components/ui/Tabler.css:8129` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 54 | `client/src/components/ui/Tabler.css:7702` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 55 | `client/src/components/ui/Tabler.css:3113` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 56 | `client/src/components/ui/Tabler.css:10705` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 57 | `client/src/components/ui/Tabler.css:9036` | css_spacing | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 58 | `client/src/components/ui/Tabler.css:15626` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |
| 59 | `client/src/components/ui/ReactTable.css:37` | css_color | TRUE | hardcoded styling value |
| 60 | `client/src/components/ui/Tabler.css:15019` | css_color | FALSE | vendored Bootstrap 4 / Tabler CSS (licence banner in file) |

## grafana

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `public/app/plugins/panel/canvas/globalStyles.ts:98` | spacing | TRUE | hardcoded styling value |
| 2 | `public/app/features/alerting/unified/triage/scene/filters/LabelsColumn.tsx:363` | spacing | TRUE | hardcoded styling value |
| 3 | `public/app/features/library-panels/styles.ts:10` | spacing | TRUE | hardcoded styling value |
| 4 | `public/app/features/alerting/unified/components/rule-editor/RuleInspector.tsx:161` | spacing | TRUE | hardcoded styling value |
| 5 | `public/app/features/datasources/components/DataSourceTypeCardList.tsx:27` | spacing | TRUE | hardcoded styling value |
| 6 | `public/app/features/admin/UpgradePage.tsx:39` | spacing | TRUE | hardcoded styling value |
| 7 | `public/app/features/alerting/unified/triage/instance-details/stateHistoryUtils.ts:9` | color | TRUE | hardcoded styling value |
| 8 | `public/app/plugins/panel/canvas/globalStyles.ts:95` | spacing | TRUE | hardcoded styling value |
| 9 | `public/app/plugins/panel/canvas/editor/inline/InlineEdit.tsx:136` | spacing | TRUE | hardcoded styling value |
| 10 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | HTML changelog string in a mock fixture (test data) |
| 11 | `public/app/features/canvas/elements/rectangle.tsx:57` | spacing | FALSE | canvas-editor element default size (user content data) |
| 12 | `public/app/features/admin/UserOrgs.tsx:233` | spacing | TRUE | hardcoded styling value |
| 13 | `public/app/plugins/panel/canvas/globalStyles.ts:220` | spacing | TRUE | hardcoded styling value |
| 14 | `public/app/plugins/panel/canvas/globalStyles.ts:97` | spacing | TRUE | hardcoded styling value |
| 15 | `public/app/features/correlations/Forms/AddCorrelationForm.tsx:28` | spacing | TRUE | hardcoded styling value |
| 16 | `public/app/features/dashboard-prompt/DashboardLandingPrompt.tsx:72` | spacing | TRUE | hardcoded styling value |
| 17 | `public/app/features/dimensions/editors/FileUploader.tsx:129` | spacing | TRUE | hardcoded styling value |
| 18 | `public/app/features/dashboard-scene/sharing/ShareButton/share-externally/ShareExternallyRenderer.tsx:233` | spacing | TRUE | hardcoded styling value |
| 19 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | mock fixture changelog (test data) |
| 20 | `public/app/features/explore/PrometheusListView/RawListItemAttributes.tsx:10` | color | TRUE | hardcoded styling value |
| 21 | `public/app/features/explore/RecentQueries/RecentQueriesFilters.tsx:172` | spacing | TRUE | hardcoded styling value |
| 22 | `public/app/features/logs/components/panel/LogLine.tsx:545` | color | TRUE | hardcoded styling value |
| 23 | `public/app/plugins/panel/canvas/editor/element/ConstraintSelectionBox.tsx:141` | color | TRUE | hardcoded styling value |
| 24 | `public/app/core/components/NestedFolderPicker/Trigger.tsx:129` | spacing | TRUE | hardcoded styling value |
| 25 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | mock fixture changelog (test data) |
| 26 | `public/app/features/logs/components/getLogRowStyles.ts:21` | spacing | TRUE | hardcoded styling value |
| 27 | `public/app/features/explore/TraceView/components/TraceTimelineViewer/SpanBar.tsx:35` | color | TRUE | hardcoded styling value |
| 28 | `public/app/features/alerting/unified/triage/scene/filters/SeverityBars.tsx:34` | spacing | TRUE | hardcoded styling value |
| 29 | `public/app/features/explore/TraceView/components/utils/color-generator.tsx:139` | color | FALSE | lookup of a data-series colour in a palette (`indexOf('#E24D42')`) |
| 30 | `public/app/features/explore/TraceView/components/TraceTimelineViewer/TimelineHeaderRow/TimelineColumnResizer.tsx:87` | spacing | TRUE | hardcoded styling value |
| 31 | `public/app/features/alerting/unified/triage/instance-details/InstanceTimeline.tsx:495` | spacing | TRUE | hardcoded styling value |
| 32 | `public/app/features/transformers/lookupGazetteer/FieldLookupTransformerEditor.tsx:26` | spacing | TRUE | hardcoded styling value |
| 33 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | mock fixture changelog (test data) |
| 34 | `public/app/features/dashboard-scene/panel-edit/PanelEditNext/QueryEditor/Header/ContentHeader.tsx:358` | spacing | TRUE | hardcoded styling value |
| 35 | `public/app/plugins/panel/canvas/editor/panZoomHelp.tsx:60` | spacing | TRUE | hardcoded styling value |
| 36 | `public/app/plugins/panel/piechart/PieChart.tsx:190` | color | TRUE | hardcoded styling value |
| 37 | `public/app/features/dimensions/editors/FileUploader.tsx:121` | spacing | TRUE | hardcoded styling value |
| 38 | `public/app/features/provisioning/Wizard/ProvisioningWizard.tsx:295` | spacing | TRUE | hardcoded styling value |
| 39 | `public/app/features/library-panels/styles.ts:11` | spacing | TRUE | hardcoded styling value |
| 40 | `public/app/features/explore/CorrelationTransformationAddModal.tsx:139` | spacing | TRUE | hardcoded styling value |
| 41 | `public/app/features/dimensions/editors/FileUploader.tsx:130` | spacing | TRUE | hardcoded styling value |
| 42 | `public/app/features/alerting/unified/styles/table.ts:29` | spacing | TRUE | hardcoded styling value |
| 43 | `public/app/features/logs/components/panel/LogListSearch.tsx:181` | spacing | TRUE | hardcoded styling value |
| 44 | `public/app/features/explore/TraceView/components/TraceTimelineViewer/SpanDetail/AccordionKeyValues.tsx:45` | spacing | TRUE | hardcoded styling value |
| 45 | `public/app/features/admin/UpgradePage.tsx:254` | spacing | TRUE | hardcoded styling value |
| 46 | `public/app/plugins/panel/nodeGraph/NodeGraph.tsx:87` | spacing | TRUE | hardcoded styling value |
| 47 | `public/app/features/canvas/elements/cloud.tsx:79` | spacing | FALSE | canvas-editor element default size (user content data) |
| 48 | `public/app/features/logs/components/panel/LogListControls.tsx:735` | spacing | TRUE | hardcoded styling value |
| 49 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | mock fixture changelog (test data) |
| 50 | `public/app/features/variables/pickers/shared/VariableOptions.tsx:171` | spacing | TRUE | hardcoded styling value |
| 51 | `public/app/plugins/panel/canvas/globalStyles.ts:34` | color | TRUE | hardcoded styling value |
| 52 | `public/app/features/dimensions/editors/URLPickerTab.tsx:59` | spacing | TRUE | hardcoded styling value |
| 53 | `public/app/features/explore/TraceView/components/TraceTimelineViewer/TimelineHeaderRow/TimelineColumnResizer.tsx:90` | spacing | TRUE | hardcoded styling value |
| 54 | `public/app/features/plugins/admin/mocks/catalogPlugin.mock.ts:729` | color | FALSE | mock fixture changelog (test data) |
| 55 | `public/app/features/explore/PrometheusListView/RawListItemAttributes.tsx:11` | color | TRUE | hardcoded styling value |
| 56 | `public/app/plugins/panel/canvas/components/connections/ConnectionAnchors.tsx:143` | color | TRUE | hardcoded styling value |
| 57 | `public/app/features/admin/UserOrgs.tsx:97` | spacing | TRUE | hardcoded styling value |
| 58 | `public/app/features/explore/TraceView/components/TraceTimelineViewer/SpanDetail/KeyValuesTable.tsx:61` | spacing | TRUE | hardcoded styling value |
| 59 | `public/app/features/alerting/unified/components/rule-editor/AnnotationsStep.tsx:248` | spacing | TRUE | hardcoded styling value |
| 60 | `public/app/features/alerting/unified/components/DynamicTableWithGuidelines.tsx:50` | spacing | TRUE | hardcoded styling value |

## budibase

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/operation/[operationId]/index.svelte:1462` | css_spacing | TRUE | hardcoded styling value |
| 2 | `packages/builder/src/pages/builder/workspace/[workspaceId]/design/[workspaceAppId]/[screenId]/_components/ComponentList/ComponentTree.svelte:301` | css_border_radius | TRUE | hardcoded styling value |
| 3 | `packages/builder/src/components/common/CodeEditor/CodeEditor.svelte:776` | css_spacing | TRUE | hardcoded styling value |
| 4 | `packages/builder/src/pages/builder/workspace/[workspaceId]/home/_components/HomeProjectTabs.svelte:224` | css_spacing | TRUE | hardcoded styling value |
| 5 | `packages/builder/src/pages/builder/_layout.svelte:401` | css_border_radius | TRUE | hardcoded styling value |
| 6 | `packages/builder/src/components/automation/SetupPanel/layouts/APIRequest.svelte:378` | css_spacing | TRUE | hardcoded styling value |
| 7 | `packages/builder/src/components/design/settings/controls/Explanation/DetailsModal/subjects/Support.svelte:33` | css_spacing | TRUE | hardcoded styling value |
| 8 | `packages/builder/src/components/automation/AutomationBuilder/FlowChart/TestDataModal.svelte:311` | css_spacing | TRUE | hardcoded styling value |
| 9 | `packages/builder/src/components/common/CodeEditor/CodeEditor.svelte:643` | css_spacing | TRUE | hardcoded styling value |
| 10 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/operation/[operationId]/index.svelte:1432` | css_spacing | TRUE | hardcoded styling value |
| 11 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/knowledge/KnowledgeTable.svelte:51` | spacing | TRUE | hardcoded styling value |
| 12 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/AgentTabList.svelte:35` | css_spacing | TRUE | hardcoded styling value |
| 13 | `packages/builder/src/pages/builder/workspace/[workspaceId]/home/_components/HomeEmptyState.svelte:211` | css_spacing | TRUE | hardcoded styling value |
| 14 | `packages/builder/src/settings/pages/auditLogs/index.svelte:559` | css_spacing | TRUE | hardcoded styling value |
| 15 | `packages/builder/src/pages/builder/workspace/[workspaceId]/design/[workspaceAppId]/[screenId]/_components/ScreenErrorsButton.svelte:100` | css_spacing | TRUE | hardcoded styling value |
| 16 | `packages/builder/src/components/common/NavItem.svelte:286` | css_spacing | TRUE | hardcoded styling value |
| 17 | `packages/builder/src/components/automation/SetupPanel/BlockHeader.svelte:289` | css_spacing | TRUE | hardcoded styling value |
| 18 | `packages/builder/src/pages/builder/_layout.svelte:404` | css_spacing | TRUE | hardcoded styling value |
| 19 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/operation/[operationId]/index.svelte:1585` | css_spacing | TRUE | hardcoded styling value |
| 20 | `packages/builder/src/pages/builder/workspace/[workspaceId]/design/[workspaceAppId]/[screenId]/_components/LeftPanel.svelte:96` | css_spacing | TRUE | hardcoded styling value |
| 21 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/operation/[operationId]/index.svelte:1456` | css_spacing | TRUE | hardcoded styling value |
| 22 | `packages/builder/src/components/common/WorkspaceSelect.svelte:501` | css_spacing | TRUE | hardcoded styling value |
| 23 | `packages/builder/src/components/common/ai/AIInput.svelte:163` | color | TRUE | hardcoded styling value |
| 24 | `packages/builder/src/components/design/settings/controls/Explanation/DetailsModal/subjects/components/Subject.svelte:44` | css_spacing | TRUE | hardcoded styling value |
| 25 | `packages/builder/src/components/design/settings/controls/ButtonActionEditor/actions/CloseScreenModal.svelte:33` | css_spacing | TRUE | hardcoded styling value |
| 26 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/AgentTabList.svelte:43` | css_spacing | TRUE | hardcoded styling value |
| 27 | `packages/builder/src/components/integration/APIEndpointViewer.svelte:1614` | css_spacing | TRUE | hardcoded styling value |
| 28 | `packages/builder/src/components/integration/APIEndpointViewer.svelte:1665` | css_border_radius | TRUE | hardcoded styling value |
| 29 | `packages/builder/src/pages/builder/auth/org.svelte:84` | css_spacing | TRUE | hardcoded styling value |
| 30 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/_layout.svelte:319` | css_spacing | TRUE | hardcoded styling value |
| 31 | `packages/builder/src/settings/pages/people/groups/_components/RemoveUserTableRenderer.svelte:54` | css_spacing | TRUE | hardcoded styling value |
| 32 | `packages/builder/src/components/automation/AutomationBuilder/FlowChart/FlowCanvas/nodes/LoopV2Node.svelte:146` | css_color | TRUE | hardcoded styling value |
| 33 | `packages/builder/src/settings/pages/connections/CreateConnection.svelte:27` | spacing | TRUE | hardcoded styling value |
| 34 | `packages/builder/src/pages/builder/workspace/[workspaceId]/activity/index.svelte:553` | css_spacing | TRUE | hardcoded styling value |
| 35 | `packages/builder/src/pages/builder/apps/index.svelte:274` | css_duration | TRUE | hardcoded styling value |
| 36 | `packages/builder/src/components/integration/RequestPanel.svelte:61` | css_border_radius | TRUE | hardcoded styling value |
| 37 | `packages/builder/src/components/common/CodeEditor/CodeEditor.svelte:824` | css_spacing | TRUE | hardcoded styling value |
| 38 | `packages/builder/src/components/usage/Usage.svelte:167` | css_spacing | TRUE | hardcoded styling value |
| 39 | `packages/builder/src/components/settings/ModalSideBar.svelte:220` | css_spacing | TRUE | hardcoded styling value |
| 40 | `packages/builder/src/components/common/CodeEditor/AIGen.svelte:119` | css_spacing | TRUE | hardcoded styling value |
| 41 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/LogComponents/LogsSessionStep.svelte:532` | css_spacing | TRUE | hardcoded styling value |
| 42 | `packages/builder/src/pages/builder/workspace/[workspaceId]/activity/index.svelte:59` | spacing | TRUE | hardcoded styling value |
| 43 | `packages/builder/src/pages/builder/workspace/[workspaceId]/home/index.svelte:1420` | css_spacing | TRUE | hardcoded styling value |
| 44 | `packages/builder/src/components/common/bindings/BindingSidePanel.svelte:492` | css_spacing | TRUE | hardcoded styling value |
| 45 | `packages/builder/src/pages/builder/workspace/[workspaceId]/home/_components/HomeControls.svelte:85` | css_spacing | TRUE | hardcoded styling value |
| 46 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/knowledge/new/SharePointSiteStepModal.svelte:115` | css_spacing | TRUE | hardcoded styling value |
| 47 | `packages/builder/src/pages/builder/workspace/[workspaceId]/design/[workspaceAppId]/[screenId]/[componentId]/_components/Component/InfoDisplay.svelte:48` | css_spacing | TRUE | hardcoded styling value |
| 48 | `packages/builder/src/components/design/settings/controls/Explanation/DetailsModal/subjects/components/JSONValue.svelte:18` | css_spacing | TRUE | hardcoded styling value |
| 49 | `packages/builder/src/settings/pages/auditLogs/index.svelte:482` | css_spacing | TRUE | hardcoded styling value |
| 50 | `packages/builder/src/pages/builder/workspace/[workspaceId]/agent/[agentId]/LogComponents/LogsSessionStep.svelte:371` | css_border_radius | TRUE | hardcoded styling value |
| 51 | `packages/builder/src/pages/builder/admin/index.svelte:172` | css_spacing | TRUE | hardcoded styling value |
| 52 | `packages/builder/src/components/design/settings/controls/IconSelect/IconSelect.svelte:273` | css_duration | TRUE | hardcoded styling value |
| 53 | `packages/builder/src/components/design/settings/controls/Explanation/Explanation.svelte:87` | css_spacing | TRUE | hardcoded styling value |
| 54 | `packages/builder/src/components/commandPalette/CommandPalette.svelte:542` | css_spacing | TRUE | hardcoded styling value |
| 55 | `packages/builder/src/pages/builder/workspace/[workspaceId]/_components/PreviewOverlay.svelte:71` | css_spacing | TRUE | hardcoded styling value |
| 56 | `packages/builder/src/components/integration/TemplateEndpointInput.svelte:192` | css_border_radius | TRUE | hardcoded styling value |
| 57 | `packages/builder/src/pages/builder/workspace/[workspaceId]/home/_components/HomeCreateMenu.svelte:99` | css_spacing | TRUE | hardcoded styling value |
| 58 | `packages/builder/src/components/automation/SetupPanel/AutomationBlockSetup.svelte:861` | css_spacing | TRUE | hardcoded styling value |
| 59 | `packages/builder/src/pages/builder/workspace/[workspaceId]/design/[workspaceAppId]/[screenId]/[componentId]/_components/Component/ConditionalUISection.svelte:96` | css_spacing | TRUE | hardcoded styling value |
| 60 | `packages/builder/src/components/common/ErrorsBox.svelte:20` | css_color | TRUE | hardcoded styling value |

## lobe-chat

| # | Location | Kind | Verdict | Note |
|---|---|---|---|---|
| 1 | `src/routes/(main)/community/(detail)/user/features/UserGroupCard.tsx:86` | css_spacing | TRUE | hardcoded styling value |
| 2 | `src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx:116` | css_spacing | TRUE | hardcoded styling value |
| 3 | `src/features/Messenger/IntegrationDetail/shared.tsx:221` | spacing | TRUE | hardcoded styling value |
| 4 | `src/features/AgentTasks/features/taskExecutionStyles.ts:31` | css_spacing | TRUE | hardcoded styling value |
| 5 | `src/features/DesktopOnboarding/steps/PermissionsStep.tsx:49` | color | TRUE | hardcoded styling value |
| 6 | `src/features/Acceptance/Workspace/AcceptanceListPanel.tsx:251` | css_spacing | TRUE | hardcoded styling value |
| 7 | `src/features/ChatInput/ControlBar/HeteroControlBar/QuotaMenu/CodexQuotaMenu.tsx:74` | css_spacing | TRUE | hardcoded styling value |
| 8 | `src/routes/(main)/community/(detail)/user/features/Header/Banner.tsx:15` | css_spacing | TRUE | hardcoded styling value |
| 9 | `src/routes/(main)/agent/features/Conversation/HeterogeneousChatInput/HeteroPlus.tsx:127` | border_radius | TRUE | hardcoded styling value |
| 10 | `src/features/ResourceManager/components/FolderTree/index.tsx:19` | css_duration | TRUE | hardcoded styling value |
| 11 | `src/features/Messenger/IntegrationDetail/shared.tsx:218` | spacing | TRUE | hardcoded styling value |
| 12 | `src/features/ChatInput/VoiceMessage/index.tsx:367` | css_spacing | TRUE | hardcoded styling value |
| 13 | `src/features/AgentGoals/GoalEmptyState.tsx:89` | css_spacing | TRUE | hardcoded styling value |
| 14 | `src/features/Messenger/IntegrationList.tsx:20` | css_spacing | TRUE | hardcoded styling value |
| 15 | `src/routes/(main)/eval/bench/[benchmarkId]/features/DatasetsTab/DatasetCard.tsx:102` | css_spacing | TRUE | hardcoded styling value |
| 16 | `src/routes/(main)/community/(detail)/user/features/UserGroupCard.tsx:76` | css_duration | TRUE | hardcoded styling value |
| 17 | `src/features/Connectors/AddConnectorModal/index.tsx:331` | spacing | TRUE | hardcoded styling value |
| 18 | `src/features/Connectors/ConnectorDetail/index.tsx:223` | spacing | TRUE | hardcoded styling value |
| 19 | `src/features/DevDock/widgets/MemoryPopover/styles.ts:87` | css_spacing | TRUE | hardcoded styling value |
| 20 | `src/features/Conversation/Messages/components/MessageBranch.tsx:43` | css_spacing | TRUE | hardcoded styling value |
| 21 | `src/features/ResourceManager/components/LibraryHierarchy/TreeSkeleton.tsx:32` | spacing | TRUE | hardcoded styling value |
| 22 | `src/features/FileViewer/Renderer/Image/Tools/Comment/index.tsx:283` | spacing | TRUE | hardcoded styling value |
| 23 | `src/features/FileViewer/Renderer/Markdown/index.tsx:24` | css_spacing | TRUE | hardcoded styling value |
| 24 | `src/features/ModelSwitchPanel/components/List/GenerationMultipleProvidersItem.tsx:78` | spacing | TRUE | hardcoded styling value |
| 25 | `src/routes/(main)/(create)/video/features/PromptInput/EditingVideoHeader.tsx:30` | css_duration | TRUE | hardcoded styling value |
| 26 | `src/features/Acceptance/Report/ReportViewer.tsx:263` | css_duration | TRUE | hardcoded styling value |
| 27 | `src/features/ResourceManager/components/Explorer/MasonryView/MasonryItem/AudioFileItem.tsx:46` | css_spacing | TRUE | hardcoded styling value |
| 28 | `src/features/MobileHome/SessionListContent/List/Item/index.tsx:138` | spacing | TRUE | hardcoded styling value |
| 29 | `src/features/HomeSidebar/Body/Agent/Modals/ConfigGroupModal/GroupItem.tsx:27` | css_spacing | TRUE | hardcoded styling value |
| 30 | `src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx:232` | css_spacing | TRUE | hardcoded styling value |
| 31 | `src/features/MCPPluginDetail/Score/TotalScore.tsx:290` | spacing | TRUE | hardcoded styling value |
| 32 | `src/features/MCP/utils.ts:131` | color | FALSE | language-to-colour data map (linguist colours) |
| 33 | `src/features/ChatInput/ControlBar/CloudRepoSwitcher.tsx:76` | css_spacing | TRUE | hardcoded styling value |
| 34 | `src/features/Settings/skill/features/LeftPanel.tsx:127` | spacing | TRUE | hardcoded styling value |
| 35 | `src/features/ResourceManager/components/Explorer/ItemDropdown/useFileItemDropdown.tsx:214` | spacing | TRUE | hardcoded styling value |
| 36 | `src/features/Conversation/ChatList/components/AutoScroll/DebugInspector.tsx:177` | spacing | TRUE | hardcoded styling value |
| 37 | `src/routes/(main)/agent/profile/features/ProfileEditor/RemoteAgentConfigCard.tsx:67` | css_spacing | TRUE | hardcoded styling value |
| 38 | `src/features/DevDock/widgets/BarButton.tsx:17` | css_spacing | TRUE | hardcoded styling value |
| 39 | `src/features/Settings/oauth-apps/features/AppDetail/RedirectUrisCard.tsx:37` | css_spacing | TRUE | hardcoded styling value |
| 40 | `src/features/Messenger/LinkModal/Telegram.tsx:32` | css_spacing | TRUE | hardcoded styling value |
| 41 | `src/features/Electron/titlebar/RecentlyViewed/styles.ts:13` | css_spacing | TRUE | hardcoded styling value |
| 42 | `src/features/DevDock/widgets/RoutePathWidget.tsx:21` | css_spacing | TRUE | hardcoded styling value |
| 43 | `src/features/ChatInput/ControlBar/BranchSwitcher.tsx:167` | css_spacing | TRUE | hardcoded styling value |
| 44 | `src/features/PageEditor/History/CompareModal/HistorySidebar.tsx:35` | css_spacing | TRUE | hardcoded styling value |
| 45 | `src/features/Integrations/Layout.tsx:9` | css_spacing | TRUE | hardcoded styling value |
| 46 | `src/features/AgentGoals/CreateGoalModal/CreateGoalContent.tsx:93` | css_spacing | TRUE | hardcoded styling value |
| 47 | `src/features/ChatInput/ControlBar/WorktreeSwitcher.tsx:156` | css_duration | TRUE | hardcoded styling value |
| 48 | `src/features/Onboarding/steps/AgentPickerStep/Skeleton.tsx:19` | spacing | TRUE | hardcoded styling value |
| 49 | `src/features/SelfLearning/Portrait/styles.ts:39` | css_spacing | TRUE | hardcoded styling value |
| 50 | `src/features/SkillStore/SkillDetail/Schema.tsx:29` | css_spacing | TRUE | hardcoded styling value |
| 51 | `src/routes/(main)/community/(detail)/group_agent/features/StatusPage/index.tsx:65` | color | TRUE | hardcoded styling value |
| 52 | `src/features/EditLock/EditingIndicator.tsx:53` | spacing | TRUE | hardcoded styling value |
| 53 | `src/features/MCP/utils.ts:139` | color | FALSE | language-to-colour data map |
| 54 | `src/features/ResourceManager/components/Explorer/SearchResultsOverlay.tsx:191` | spacing | TRUE | hardcoded styling value |
| 55 | `src/features/FileViewer/Renderer/Image/Tools/styles.ts:96` | css_spacing | TRUE | hardcoded styling value |
| 56 | `src/libs/better-auth/email-templates/workspace-invite.ts:32` | color | TRUE | hardcoded styling value |
| 57 | `src/features/AgentGoals/GoalDecision/index.tsx:192` | spacing | TRUE | hardcoded styling value |
| 58 | `src/features/LocalFile/LocalFolder.tsx:28` | css_spacing | TRUE | hardcoded styling value |
| 59 | `src/features/AgentSidebar/Topic/List/TopicListSkeleton.tsx:23` | spacing | TRUE | hardcoded styling value |
| 60 | `src/features/AgentGoals/ProcessControl/Frontier.tsx:86` | css_spacing | TRUE | hardcoded styling value |

_Last updated: 2026-10-09_
