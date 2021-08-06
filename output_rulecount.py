import kbtransform
rules = kbtransform.loadall(silent=True)

for k, ruleset in rules.items():
    print(k, ruleset)
