# generate datalog
import os
import os.path
import kbtransform
from tqdm import tqdm
from collections import defaultdict

import soccerdb

rules = kbtransform.loadall(silent=True)
print(rules)

conn = soccerdb.connect()

matches_with_eventdata = soccerdb.matches_with_events()
match_count = soccerdb.count()
print("matches", match_count)
print("matches with event data", matches_with_eventdata.shape[0])
event_type = defaultdict(int)
event_count = defaultdict(int)

DOLIMIT = 1000
count = 0
for match_id in tqdm(matches_with_eventdata.id):
    count += 1
    match = soccerdb.get_match_data(match_id)

    # skip previously generated matches
    filename = "data/generated/datalog/match_report_%s.dl" % match.match_id
    if os.path.exists(filename):
        continue

    # print(match_id, match, filename)
    soccerdb.fill_events(match)
    match_event_count = len(match.events)

    event_count[match_event_count] += 1

    ruleset = rules["datalog"]

    try:
        transformed_match, _ = ruleset.transform(
            "datalog", context=match, sampling=False
        )
        transformed_match = transformed_match.strip().split("\n")
        transformed_match = "\n".join(
            map(lambda line: "%s" % line.strip(), transformed_match)
        )

        content = [transformed_match, ""]
        prevline = None

        for idx, evt in enumerate(match.events):
            if evt.get("del", None) == "1":
                continue
            if evt.get("invalid", False):
                continue
            transformed_event, _ = ruleset.transform(
                "datalog", context=evt, sampling=False, doraise=True, match=match
            )
            transformed_event = transformed_event.strip().split("\n")
            transformed_event = "\n".join(
                map(lambda line: "%s" % line.strip(), transformed_event)
            )

            line = "{%s}\n" % transformed_event
            if prevline is not None and prevline == line:
                continue

            content.append(line)
            prevline = line
            # print(idx, transformed_event)

        content.append("\n")

        with open(filename, "wt") as outfile:
            outfile.write("\n")
            outfile.write(";;# data\n")
            outfile.write("[\n")
            outfile.write("\n".join(content))
            outfile.write("]\n\n")
    except Exception as e:
        print(filename, "failed")
        raise e

soccerdb.disconnect()
