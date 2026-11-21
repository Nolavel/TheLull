# BP_CoreExposureZone — spatial exposure fixture
Package: /Game/Survival/Environment/BP_CoreExposureZone
AssetType: Blueprint Class
ParentClass: Actor
DependsOn: none
Status: NEEDS REVIEW / NOT ASSEMBLED / PIE NOT RUN, 21.11.2026. One asset, no Tick.
 
## Components and placement
DefaultSceneRoot → Box Collision "ExposureBox" (Box Extent 250,250,180 cm). In level place center at (known floor location + 100 cm vertical), on a walkable flat part of stock map, player starts outside. Optional nearby existing primitive geometry marks protected area, no geography. Box collision Query Only; object type WorldDynamic; all channels Ignore except Pawn Overlap; Generate Overlap Events=true. Verify stock pawn capsule generates overlap; do not change project-wide collision defaults. Box not blocking movement. Editor label "Protected fixture"; not real fire/shelter yet.
 
## Variables / functions
OutsideFeelsLikeC: Float (double precision), default -10.0; InsideFeelsLikeC same, default 5.0. Both private class defaults, not exposed or editable per instance in this fixture. Owner is zone; body only reads. No saved state.
QueryExposure(Subject: Actor Object Reference) -> FeelsLikeC: Float (double precision), bInside: Boolean, bValid: Boolean (pure, no side effects).
 
## Function graph
```text
function QueryExposure(Subject) {
    if (NOT IsValid(Subject)) return (OutsideFeelsLikeC,false,false)
    let Inside = ExposureBox.IsOverlappingActor(Other=Subject)
    if (Inside) return (InsideFeelsLikeC,true,true)
    return (OutsideFeelsLikeC,false,true)
}
```
One cached result per call in caller; use component node, not actor-wide collision. Actual returned pin names/purity confirm 5.8.4/MCP. No overlap counter and no direct write to body. On Component Begin Overlap/End Overlap (optional preview only) can request level refresh; first pass does **not** require these events because authoritative exposure sampled before each sim step.
 
## PIE
Walk outside then inside then exit; QueryExposure returns -10/5/-10, pawn remains mobile, no duplicate body. Standing inside at warm cap does not raise value above 1; after prior cold loss, entering protected space and paying time increases warmth. At pause no needs change until next step. Source: [Epic 5.8 UPrimitiveComponent](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/UPrimitiveComponent?application_version=5.8), [Actor IsOverlappingActor](https://dev.epicgames.com/documentation/unreal-engine/BlueprintAPI/Collision/IsOverlappingActor) (do not confuse with component version), [Core research](../../../../../gameplay/reference/CORE_BODY_UI_TO_UE.md).
