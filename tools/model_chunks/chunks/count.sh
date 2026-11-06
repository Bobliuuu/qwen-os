#!/bin/bash
cd /Users/jhome/qwenos-work/out/model/chunks
python3 - <<'PY'
import json,os
n=0;miss=[]
for i in range(35):
    c='c%02d'%i; ok=False
    for d in ('prod1','prod1p','.'):
        try:
            r=json.load(open(f'{d}/{c}/result.json'))
            if r.get('mode')=='MODEL': ok=True;break
        except Exception: pass
    n+=ok
    if not ok: miss.append(c)
print(n,' '.join(miss))
PY
