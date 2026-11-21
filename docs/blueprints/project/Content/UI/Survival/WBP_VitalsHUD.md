# WBP_VitalsHUD — minimal UI

Package: /Game/UI/Survival/WBP_VitalsHUD
AssetType: Widget Blueprint
DependsOn: ST_CoreVitals
Status: stencil drafted / NEEDS REVIEW, 21.11.2026. Actual UE 5.8.4 pins/MCP/PIE not verified. [Research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).

ParentClass: UserWidget
Designer: Canvas root, bottom-left anchor, margin 24; VerticalBox, five horizontal rows (TextBlock labels, SizeBox 120×12 with ProgressBar, trend TextBlock). PB_Warmth/PB_Rest/PB_Thirst/PB_Hunger/PB_Condition and TR_Warmth/TR_Rest/TR_Thirst/TR_Hunger/TR_Condition mark Is Variable. Root Not Hit-Testable (Self & All Children). No tick/bindings/shaders.
 
RenderVitals(Snapshot: ST_CoreVitals) -> no output, impure function. For each row Break Snapshot once, Set Percent from corresponding 0..1 raw value (UMG takes single precision; convert if needed). Set Fill Color and Opacity neutral when >.25, amber when >0 and <=.25, red when zero. Text trend from actual delta: <-1e-6 "↓", >1e-6 "↑", else "—". Labels or shape convey empty without relying on color. No separate cold bar. No authoritative state or clock. Initial render explicit; event-driven updates from level/body dispatcher.
 
PIE: initial all full; 1h cold results 60/94/92/95/100 percent; warm exposure makes warmth rise while other needs decrease; zero visibly depleted; no duplicate widget, no blocked camera controls. Verify 720p/1080p. No actual asset yet.
