# ST_CoreSupplies — finite starting food and water

Package: /Game/Survival/Actions/ST_CoreSupplies
AssetType: Blueprint Structure (User Defined Struct)
ParentClass: n/a
DependsOn: none
Status: NEEDS REVIEW / NOT ASSEMBLED / NOT PIE TESTED. 21.11.2026.

## Fields (exact UE property identifiers)
| Name | UE type | Default | Meaning |
|---|---|---:|---|
| WaterServings | Integer (int32) | 0 | finite usable drinks |
| FoodServings | Integer (int32) | 0 | finite usable food portions |
| LastStockChange | String | "Uninitialized" | debug-only explanation |

BPC_CoreActions is the single authoritative owner of the live struct. UI gets a value copy; never edits counts. InitializeCoreActions explicitly seeds **2 WaterServings + 1 FoodServings** in the test level; struct defaults remain zero so an accidentally uninitialized owner has no free supplies. Physical liters, calories, spoilage and stack instances are future inventory work. One serving is an artificial fixture unit, NOT a measured TLD ration or Key West resource.

### Editor construction
Create Blueprints → Structure at exact package path, add fields/types/defaults above, Save. Validate Make/Break node and GetStock return pin. No Tick, no other new asset required.