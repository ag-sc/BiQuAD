# generate questions
import json
import random
import traceback
import os
import os.path
import kbtransform
from tqdm import tqdm
from collections import defaultdict
from generate_unanswerable import load_file
from execdatalog import run_datalog
import soccerdb


rules = kbtransform.loadall(silent=True)
conn = soccerdb.connect()

matches_with_eventdata = soccerdb.matches_with_events()
match_count = soccerdb.count()
print("matches", match_count)
print("matches with event data", matches_with_eventdata.shape[0])
event_type = defaultdict(int)
event_count = defaultdict(int)

MIN_REPORT_LEN = 50

DOLIMIT = 10
count = 0

# iterate over all qualified matches with event data
for match_id in tqdm(matches_with_eventdata.id):
    count += 1
    match = soccerdb.get_match_data(match_id)
    match_generated = 0

    # load match report as text and datalog
    # this filters out matches that don't contain sufficient data and skips these matches
    report_filename = "data/generated/reports/match_report_%s.txt" % match.match_id
    datalog_filename = "data/generated/datalog/match_report_%s.dl" % match.match_id
    if not os.path.exists(datalog_filename):
        print("no datalog file")
        continue
    report_content = load_file(report_filename)
    report_content = list(filter(lambda l: l.strip() != '', report_content))
    print("report length", len(report_content))
    filename = "data/generated/questions/questions_%s.dat" % match.match_id

    if len(report_content) < MIN_REPORT_LEN:
        print("SKIP(report len)", filename)
        continue

    if os.path.exists(filename):
        print("SKIP", filename)
        continue

    datalog_content = load_file(datalog_filename)
    datalog_content = list(filter(lambda l: l.strip() != '', datalog_content))
    if len(datalog_content) < MIN_REPORT_LEN:
        print("SKIP(datalog len)", filename)
        continue

    datalog_content = "\n".join(datalog_content)

    soccerdb.fill_events(match)
    match_event_count = len(match.events)

    event_count[match_event_count] += 1

    ruleset = rules['questions']

    generated_q_ids = set()

    try:
        content = []

        for gen_attempt in range(20):
            transformed_match = ruleset.transform("text", context=match, return_rule=True, doraise=False, sampling=True)
            transformation_rule = transformed_match[2]
            transformation_rule_id = transformation_rule.get_precondition("id", None)
            transformed_match = transformed_match[0]

            transformed_match = transformed_match.strip().split("\n")
            if transformed_match is None or len(transformed_match) == 0:
                continue
            transformed_match = "\n".join(map(lambda line: "%s" % line.strip(), transformed_match))
            transformed_match = random.choice(transformed_match.split("\n"))

            cur_rule_category = transformation_rule.get_precondition("category", "-")
            partner_rule = ruleset.get("datalog", transformation_rule_id)
            if partner_rule is None:
                raise Exception("Could not find matching id=%s" % transformation_rule_id)
            partner_transformed, _, _ = ruleset.transform("datalog", context=match, return_rule=True, doraise=True, sampling=True, applicable_rules=[partner_rule])
            partner_req_propagation = partner_rule.get_precondition("propagate", None)
            print("PARTNER", partner_transformed)

            if transformation_rule_id not in generated_q_ids:
                transformed_match = transformed_match.strip()
                partner_transformed = partner_transformed.strip()
                print("QUERYING", partner_transformed)
                query_result = run_datalog(datalog_content, partner_transformed, [])
                content_obj = {
                        'category': cur_rule_category,
                        'rule': transformation_rule_id,
                        'question': transformed_match,
                        'datalog': partner_transformed,
                        'answer': query_result
                        }
                content.append(json.dumps(content_obj))

                generated_q_ids.add(transformation_rule_id)
            match_generated += 1

        prevline = None

        events = match.events
        random.shuffle(events)

        for idx, evt in enumerate(match.events):
            print()
            print()
            print()
            if match_generated > 50:
                print("hit upper limit")
                break

            if evt.get("del", None) == '1':
                continue
            if evt.get("invalid", False):
                continue
            transformed_event = ruleset.transform("text", context=evt, sampling=True, doraise=False, return_rule=True, match=match)

            if transformed_event is None or transformed_event[0] is None:
                continue

            transformation_rule = transformed_event[2]
            transformation_rule_id = transformation_rule.get_precondition("id", None)
            cur_rule_category = transformation_rule.get_precondition("category", "-")
            cur_rule_answertype = transformation_rule.get_precondition("answertype", "-")
            transformed_event = transformed_event[0]
            if transformed_event is None:
                continue
            transformed_event = transformed_event.strip().split("\n")
            transformed_event = "\n".join(map(lambda line: "%s" % line.strip(), transformed_event))
            transformed_event = random.choice(transformed_event.split("\n")).strip()

            partner_rule = ruleset.get("datalog", transformation_rule_id)
            if partner_rule is None:
                raise Exception("Could not find matching id=%s" % transformation_rule_id)
            partner_transformed_event, _, _ = ruleset.transform("datalog", context=evt, return_rule=True, doraise=True, sampling=True, applicable_rules=[partner_rule])

            partner_transformed_event = partner_transformed_event.strip()
            print("QUERYING", partner_transformed_event)
            query_result = run_datalog(datalog_content, partner_transformed_event, [])

            if query_result is None or query_result.strip() == '':
                continue

            line = "Category:\n%s\n\nRule:\n%s\n\nQuestion:\n%s\n\nDatalog:\n%s\n\nResult:\n%s\n" % (cur_rule_category, transformation_rule_id, transformed_event, partner_transformed_event, query_result)

            partner_req_propagation = partner_rule.get_precondition("propagate", None)
            print(line)

            if prevline is not None and prevline == line:
                continue

            if transformation_rule_id not in generated_q_ids:
                generated_q_ids.add(transformation_rule_id)
                content_obj = {
                        'category': cur_rule_category,
                        'rule': transformation_rule_id,
                        'question': transformed_event,
                        'datalog': partner_transformed_event,
                        'answer': query_result,
                        'answertype': cur_rule_answertype,
                        }
                content.append(json.dumps(content_obj))
                match_generated += 1
                prevline = line

        content.append("\n")

        with open(filename, "wt") as outfile:
            outfile.write("\n".join(content))
    except Exception as e:
        print(filename, "failed:", e)
        traceback.print_exc()

soccerdb.disconnect()
