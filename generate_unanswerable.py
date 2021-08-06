import random
from execdatalog import run_datalog
import random
import os
import os.path
from tqdm import tqdm
from glob import glob
from collections import defaultdict
from string import digits
import json


def load_file(filename):
    """
    Utility to load a content file
    """
    content = []
    with open(filename, "rt") as infile:
        for line in infile:
            content.append(line.strip())
    return content


BASEPATH = "./data/generated/"
REPORTS = BASEPATH + "reports/*.txt"
DATALOGS = BASEPATH + "datalog/*.dl"
QUESTIONS = BASEPATH + "questions/*.dat"
FULLQUESTION_TARGET = BASEPATH + "questionsfull"

remove_digits = str.maketrans("", "", digits)
stripchars = set([c for c in ".-:;!@#$%%^&*(){}"])


def tokenize(line):
    line = line.strip().lower()
    line = line.translate(remove_digits)
    line = "".join(c for c in line if not c in stripchars)
    line = line.split(" ")
    line = list(filter(lambda t: t != "", map(str.strip, line)))
    return line


sentences = defaultdict(int)
doc_length = defaultdict(int)
doc_unique_tokens = defaultdict(int)
top_terms = defaultdict(int)


def describe(name, dic, n=10):
    top_n = []
    restcount = 0
    for i, k in enumerate(sorted(dic, key=dic.get, reverse=True)):
        if i < n:
            top_n.append([k, dic[k]])
        else:
            restcount += dic[k]
    description = []
    for k, v in top_n:
        description.append("%s: %s" % (k, v))

    print(name, ", ".join(description), "rest", restcount)


def main_stats():
    for filename in tqdm(glob(REPORTS)):
        fbase = os.path.basename(filename)
        content = load_file(filename)
        content = list(filter(lambda l: l.strip() != "", content))
        sentences[len(content)] += 1

        content = [tokenize(line) for line in content]
        unique_tokens = set()
        token_count = 0
        for sentence in content:
            for token in sentence:
                top_terms[token] += 1
                unique_tokens.add(token)
                token_count += 1

        doc_unique_tokens[len(unique_tokens)] += 1
        doc_length[token_count] += 1

    describe("sentences", sentences)
    describe("doc length", doc_length)
    describe("unique tokens", doc_unique_tokens)
    describe("top terms", top_terms)


def load_questions(filename):
    lines = load_file(filename)
    content = []
    for line in lines:
        line = line.strip()
        if line == "":
            continue
        content.append(json.loads(line))
    return content


def random_questions(available, not_filename):
    selected = None
    while selected is None or selected == not_filename:
        selected = random.choice(available)
    return selected, load_questions(selected)


def main_unanswerable():
    filelist = glob(QUESTIONS)
    random.shuffle(filelist)
    all_question_files = list(filelist)
    available_question_files = list(all_question_files)  # working copy

    for filename in tqdm(all_question_files):
        fbase = os.path.basename(filename)
        target = os.path.join(FULLQUESTION_TARGET, fbase)
        if os.path.exists(target):
            continue

        datalog_filename = os.path.join(
            BASEPATH,
            "datalog/",
            fbase.replace(".dat", ".dl").replace("questions_", "match_report_"),
        )
        datalog_content = load_file(datalog_filename)
        datalog_content = list(filter(lambda l: l.strip() != "", datalog_content))
        datalog_content = "\n".join(datalog_content)

        content = load_questions(filename)
        to_generate = int(len(content) / 4)
        print(fbase, len(content), to_generate)

        generated_unanswerable = []
        while len(generated_unanswerable) <= to_generate:
            other_fname, other = random_questions(available_question_files, filename)
            print("other", other_fname)
            other_random = random.choice(other)
            other_question = other_random["question"]
            other_query = other_random["datalog"]
            print(other_question, other_query)

            query_result = run_datalog(
                datalog_content, other_query, [], silent=True
            ).strip()
            if not query_result == "":
                continue

            # unanswerable question found
            other_random["unanswerable"] = True
            other_random["answer"] = ""

            generated_unanswerable.append(other_random)

        with open(target, "wt") as outfile:
            for q in content:
                if "category" in q and q["category"] == "-":
                    q["category"] = "Simple"
                outfile.write("%s\n" % json.dumps(q))
            for q in generated_unanswerable:
                if "category" in q and q["category"] == "-":
                    q["category"] = "Simple"
                outfile.write("%s\n" % json.dumps(q))


if __name__ == "__main__":
    # main_stats()
    main_unanswerable()
