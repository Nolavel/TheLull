"""Small human-in-the-loop day/night prototype for two interacting needs.

Only shelter choices are human-operated; the single house expedition and
night controller are still scripted. This is exploratory, not a fun detector.

python3 -m lab.coupled_playtest --variant A_safe --wet --need-water --json local-session.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .coupled_microloop import run

def run_session(seed: int=1, variant: str="A_safe", profile: str="local",
                *, wet: bool=True, need_water: bool=True,
                ask=input, show=print) -> dict:
    show("TheLull — один день и ночь. Выбираешь действия в убежище.")
    show("Вылазка и ночь пока частично автоматические. Нет правильного ответа.")
    intention=ask("Какую собственную задачу хочешь решить в этот день? ").strip()
    answers=[]

    def choose(d):
        show(f"\n{d.time} | {d.point} | цель персонажа: {d.intention}")
        for cue in d.cues:
            show("  "+cue)
        options=[o for o in d.alternatives if o["available"]]
        for i,op in enumerate(options,1):
            show(f"  {i}. {op['option']} — время около {op['expected_duration_h']} ч"
                 f", предполагаемый расход {op['expected_fuel_spent']:.2f} дров")
        while True:
            raw=ask("Что выбираешь (номер)? ").strip()
            if raw.isdecimal() and 1<=int(raw)<=len(options):
                selected=options[int(raw)-1]["option"]
                break
            show("Нужно выбрать доступный номер.")
        expected=ask("Что ожидаешь получить/потерять этим действием? ").strip()
        why=ask("Почему выбрал именно это? ").strip()
        answers.append({"point":d.point,"time":d.time,"action":selected,
                        "expected_outcome_before":expected,"reason_before":why})
        return selected

    human=run(seed, variant, profile, wet=wet, need_water=need_water,
              policy="agent",provider=choose)
    show("\nИтог сценария:")
    show(f"Прошло {human['elapsed_minutes']/60:.2f} ч; "
         f"тело {human['core_final']:.2f} °C; "
         f"топливо {human['fuel_final']:.2f}; "
         f"одежда: мокрота {human['wet_final']:.2f}; "
         f"вода: {human['safe_water_final']} приготовлено.")
    interview={
      "what_was_clear":ask("Что было понятно, а что нет? ").strip(),
      "what_caught_attention":ask("Что заинтересовало или удивило? Если ничего — так и скажи. ").strip(),
      "what_was_tedious":ask("Что показалось рутиной или раздражало? ").strip(),
      "own_next_intention":ask("Что ты бы сам захотел сделать дальше? Можно ответить 'ничего'. ").strip(),
      "would_try_again_and_why":ask("Хочешь попробовать другой способ? Почему да или нет? ").strip(),
    }
    baseline=run(seed,variant,profile,wet=wet,need_water=need_water,policy="agent")
    return {
        "design":"textual coupled day/night human microtest; no real map or visual game",
        "conditions":{"seed":seed,"variant":variant,"profile":profile,
                      "wet":wet,"need_water":need_water},
        "human_input_before":intention,
        "human_choice_notes":answers,
        "human_story":human,
        "same_seed_agent_story":baseline,
        "interview":interview,
        "note":"Human evidence only after a real person completes the session; CI mocks do not count.",
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",type=int,default=1)
    ap.add_argument("--variant",choices=("A_safe","B_readable","C_unreadable"),
                    default="A_safe")
    ap.add_argument("--profile",choices=("local","novice"),default="local")
    ap.add_argument("--wet",action="store_true")
    ap.add_argument("--need-water",action="store_true")
    ap.add_argument("--json",type=Path,required=True)
    args=ap.parse_args()
    data=run_session(args.seed,args.variant,args.profile,wet=args.wet,
                     need_water=args.need_water)
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Сохранено локально: {args.json} (ответы человека — не публикуй без согласия).")


if __name__=="__main__":
    main()
