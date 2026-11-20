# BP_LogicTest (Blueprint)

Package: /Game/Tests/BP_LogicTest
ParentClass: /Script/Engine.Actor

Проверочный ассет: по нему сверяем, что облачный агент восстанавливает логику из `.uasset` вслепую.
Игровой ценности не несёт, в игру не попадает.

### Variables

- bIsCold: bool = false [Instance Editable]

### Components

(нет)

### Event graph EventGraph

```
event ReceiveBeginPlay() [override] {
    if (bIsCold) {
        PrintString(InString: "Cold")
    } else {
        PrintString(InString: "Warm")
    }
}
```
