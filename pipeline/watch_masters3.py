"""Watches montazh-cloud/out for any new or changed RL-*-1.15*.mp4 master file (any variant suffix, e.g. -b),
fires when the file has been stable for STABLE seconds. State keyed by file name."""
import os, sys, time, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
OUT = r'C:\Ferma\factory\montazh-cloud\out'
SEEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seen4.json')
STABLE = 600


def scan():
    res = {}
    for d in (OUT, os.path.join(OUT, '\u0570\u0580\u0561\u057a\u0561\u0580\u0561\u056f\u057e\u0561\u056e')):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.startswith('RL-') and '-1.15' in f and f.endswith('.mp4'):
                res[f] = os.path.join(d, f)
    return res


if os.path.exists(SEEN):
    seen = json.load(open(SEEN, encoding='utf-8'))
else:
    seen = {f: os.path.getmtime(p) for f, p in scan().items()}  # everything present now is already processed
    json.dump(seen, open(SEEN, 'w', encoding='utf-8'))
while True:
    for f, p in sorted(scan().items()):
        m = os.path.getmtime(p)
        if f in seen and abs(seen[f] - m) < 1:
            continue
        if time.time() - m < STABLE:
            continue
        new = f not in seen
        seen[f] = m
        json.dump(seen, open(SEEN, 'w', encoding='utf-8'))
        print('%s: %s  %.1f MB, stable %d min' % ('NEW' if new else 'CHANGED', f, os.path.getsize(p) / 1048576, (time.time() - m) / 60))
    time.sleep(20)
