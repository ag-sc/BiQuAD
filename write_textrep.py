import os
import os.path
import kbtransform
import sys
from collections import defaultdict
from tqdm import tqdm

import soccerdb

rules = kbtransform.loadall(silent=True)
print(rules)

conn = soccerdb.connect()
matches_with_eventdata = soccerdb.matches_with_events()
match_count = soccerdb.count()
print("matches", match_count)
print("matches with event data", matches_with_eventdata.shape[0])
event_type = defaultdict(int)

count = 0


def write_transform(ruleset, match, filename):
    try:
        transformed_match, _ = ruleset.transform(
            "textrep", context=match, sampling=True
        )
        transformed_match = transformed_match.strip()
        content = [transformed_match, ""]
        prevline = None
        prev_replacements = None

        for idx, evt in enumerate(match.events):
            # skip deleted or invalid event entries
            if evt.get("del", None) == "1":
                continue
            if evt.get("invalid", False):
                continue
            transformed_event, prev_replacements = ruleset.transform(
                "textrep",
                context=evt,
                sampling=True,
                doraise=True,
                match=match,
                previous_replacements=prev_replacements,
            )
            if "coref" in prev_replacements:
                # disable multiple corefs right after each other
                prev_replacements = {}
            transformed_event = transformed_event.strip()
            line = "%s: %s" % (evt["minute"], transformed_event)
            if prevline is not None and prevline == line:
                continue

            content.append(line)
            prevline = line
            # print(idx, transformed_event)

        content.append("\n")

        with open(filename, "wt") as outfile:
            outfile.write("\n".join(content))
    except Exception as e:
        print(filename, "failed")
        raise e


ruleset = rules["textrep"]
for match_id in tqdm(matches_with_eventdata.id):
    match = soccerdb.get_match_data(match_id)

    # skip matches we already generated a report on
    filename = "data/generated/reports/match_report_%s.txt" % match.match_id
    if os.path.exists(filename):
        continue

    count += 1
    soccerdb.fill_events(match)

    print("generating", filename)
    write_transform(ruleset, match, filename)

    if count > 0 and count % 500 == 0:
        print("done chunk", count)
        sys.exit(0)

soccerdb.disconnect()

sys.exit(0)
