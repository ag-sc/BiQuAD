import json
import random
import os
import os.path
from tqdm import tqdm
from glob import glob
from collections import defaultdict

BASEPATH = "./data/generated-content/"
REPORTS = BASEPATH + "reports/*.txt"
DATALOGS = BASEPATH + "datalog/*.dl"
FULLQUESTIONS = BASEPATH + "questions/*.dat"
stats = defaultdict(int)


def load_file(filename, strip_empty=True):
    """
    Returns the content of `filename`, by default all empty lines are discarded.
    """
    content = []
    with open(filename, "rt") as infile:
        for line in infile:
            content.append(line.strip())

    if strip_empty:
        content = list(filter(lambda l: l.strip() != "", content))

    return content


def unquote(val):
    if val is None:
        raise Exception("empty value")
    val = str(val)
    for i in range(2):
        if val.startswith("'"):
            val = val[1:]
        if val.endswith("'"):
            val = val[:-1]
        if val.startswith('"'):
            val = val[1:]
        if val.endswith('"'):
            val = val[:-1]
    val = val.replace("\\'", "'")
    return val


def add_answers(context, qapair, qa, numeric_answers):
    answer = unquote(qa["answer"])
    answertype = qa["answertype"]
    minute = qa.get("minute", None)
    qanswer = {"text": answer, "answer_start": -1}

    first_line = context.strip()
    first_line = first_line[: first_line.index("\n")]

    target = qapair["answers"]

    if answertype == "minute":
        if answer == "":
            return False
        minquery = "\n%s: " % answer
        if minquery not in context:
            import pdb

            pdb.set_trace()
        qcopy1 = dict(qanswer)
        qcopy1["answer_start"] = context.index(minquery) + 1
        qcopy2 = dict(qcopy1)
        qcopy2["text"] = "%s:" % answer
        target.append(qcopy1)
        target.append(qcopy2)
    elif answertype == "numeric":
        if answer == "":
            raise Exception("empty numeric answer")
        qcopy = dict(qanswer)
        qcopy["text"] = answer
        numeric_answers.append([answer, qcopy])
        target.append(qcopy)
    elif answertype == "text":
        qcopy = dict(qanswer)

        if minute is None and answer in context and context.index(answer) > -1:
            qcopy["answer_start"] = context.index(answer)
            target.append(qcopy)
        elif minute is None and answer.split(" ")[-1] in context:
            answer = answer.split(" ")[-1]
            qcopy["text"] = answer
            onset = context.index(answer)
            while onset > -1:
                qcopy1 = dict(qcopy)
                qcopy1["answer_start"] = onset
                target.append(qcopy1)
                onset = context.find(answer, onset + 1)

        elif minute is None and not answer.split(" ")[-1] in context:
            stats["skip_nomin_ans_not_found"] += 1
            return False
        elif minute is not None:
            minquery = "\n%s: " % minute
            onset = context.index(minquery) + 1
            nextmatch = context.find(answer, onset)
            if nextmatch is None or nextmatch < 0:
                nextmatch = context.find(answer.split(" ")[-1], onset)
                answer = answer.split(" ")[-1]
                if nextmatch is None or nextmatch < 0:
                    answer = unquote(qa["answer"])
                    nextmatch = context.find(answer)
                    if nextmatch is None or nextmatch < 0:
                        if (
                            not answer in context
                            and not answer.split(" ")[-1] in context
                        ):
                            return False
                        import pdb

                        pdb.set_trace()
            qcopy1 = dict(qanswer)
            qcopy1["text"] = answer
            qcopy1["answer_start"] = nextmatch
            target.append(qcopy1)

            if ":event/player" in qa["datalog"] and ":event/team" not in qa["datalog"]:
                # might be a name
                if " " in answer:
                    alternative = answer.split(" ")[-1]
                    qcopy2 = dict(qanswer)
                    qcopy2["text"] = alternative
                    nextmatch = context.find(alternative, onset)
                    qcopy2["answer_start"] = nextmatch
                    target.append(qcopy2)

    assert len(target) != 0


def handle_numeric_answers(context, numeric_answers):
    if numeric_answers is None or len(numeric_answers) == 0:
        return context

    min_numeric_count = 5
    all_values = [int(x[0]) for x in numeric_answers]

    while len(all_values) < min_numeric_count:
        candidate = random.randint(0, 100)
        if candidate in all_values:
            continue
        all_values.append(candidate)

    all_values.sort()
    nums = " ".join(["NUM%s" % num for num in all_values])

    onset = len(context)
    context += "\n\n" + nums

    for numval, qanswer in numeric_answers:
        qanswer["answer_start"] = context.find("NUM%s" % numval, onset) + 3

    return context


def main():
    print("starting export")

    all_qa_files = list(glob(FULLQUESTIONS))
    random.shuffle(all_qa_files)
    doc_count = len(all_qa_files)
    splits = list(map(int, [doc_count * 0.6, doc_count * 0.2, doc_count * 0.2]))
    print("60-20-20 split size", splits, "total", doc_count)
    for idx in range(len(splits)):
        if idx > 0:
            splits[idx] += splits[idx - 1]
    print("60-20-20 splits", splits, "total", doc_count)
    split_ids = ["train", "dev", "test"]
    split_active = 0

    target_data = {}
    for s in split_ids:
        target_data[s] = []

    file_idx = 0
    for filename in tqdm(all_qa_files):
        fbase = os.path.basename(filename)
        qa_content = load_file(filename, strip_empty=True)
        qa_content = list(map(json.loads, qa_content))

        split_id = split_ids[split_active]

        print(split_id, fbase)
        # ['category', 'rule', 'question', 'datalog', 'answer', 'unanswerable']

        text_content = load_file(
            os.path.join(
                BASEPATH,
                "reports",
                fbase.replace("questions_", "match_report_").replace(".dat", ".txt"),
            ),
            strip_empty=False,
        )
        text_content = "\n".join(text_content)

        datalog_content = load_file(
            os.path.join(
                BASEPATH,
                "datalog",
                fbase.replace("questions_", "match_report_").replace(".dat", ".dl"),
            ),
            strip_empty=False,
        )
        datalog_content = "\n".join(datalog_content)

        target_data[split_id].append([qa_content, text_content, datalog_content])

        file_idx += 1
        if file_idx == splits[split_active]:
            split_active += 1
            if split_active >= len(splits):
                split_active = len(splits) - 1

    for split_id in split_ids:
        split_documents = []

        for qa_content, text_content, datalog_content in target_data[split_id]:
            doc_title = text_content.strip().split("\n")[0]
            doc = {"title": doc_title, "paragraphs": []}

            doc_para = {
                "context": text_content.strip(),
                "datalog": datalog_content.strip(),
            }
            para_qas = []

            numeric_answers = []

            for qa in qa_content:
                qapair = {}

                if qa["rule"] == "Q_A_2":
                    qa["answertype"] = "numeric"

                qapair["rule"] = qa["rule"]
                qapair["category"] = qa["category"]
                qapair["question"] = qa["question"]
                qapair["answertype"] = qa["answertype"]
                qapair["datalog"] = qa["datalog"]
                qapair["id"] = "%s_%s" % (
                    qa["rule"],
                    random.randint(10000000, 99999999),
                )

                qapair["is_impossible"] = qa.get("unanswerable", False)
                qapair["answers"] = []

                do_add = True
                if not qapair["is_impossible"]:
                    add_res = add_answers(
                        doc_para["context"], qapair, qa, numeric_answers
                    )
                    if add_res == False:
                        stats["skipped"] += 1
                        do_add = False

                if do_add:
                    para_qas.append(qapair)
                    stats["added"] += 1
                    stats["%s_added" % split_id] += 1

            # handle and generate numeric_answers as multiple choice
            context = handle_numeric_answers(doc_para["context"], numeric_answers)
            doc_para["context"] = context

            doc_para["qas"] = para_qas

            doc["paragraphs"].append(doc_para)
            split_documents.append(doc)

        output = {"version": "2.0", "split": split_id, "data": split_documents}
        with open("./biquad-%s.json" % split_id, "wt") as outfile:
            json.dump(output, outfile, sort_keys=False, indent=2)

    print(stats)
    print("all done")


if __name__ == "__main__":
    main()
