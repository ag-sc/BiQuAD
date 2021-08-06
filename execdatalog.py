import os
import subprocess
import json


def load_file(filename):
    content = []
    with open(filename, "rt") as infile:
        for line in infile:
            content.append(line.strip())
    return content


SECTION_DATA = ";;# data"
SECTION_QUERY = ";;# query"
SECTION_ARGS = ";;# args"

# the path to the node.js based datalog helper
BINPATH = "./dltools/nodeinterp/"


def run_datalog(kb, query, inputs, silent=False, subresults=False):
    fullinput = ""

    if SECTION_DATA not in kb:
        fullinput += SECTION_DATA + "\n"
    fullinput += kb
    fullinput += "\n"

    if not type(inputs) is str:
        inputs = json.dumps(inputs)

    if SECTION_QUERY not in inputs:
        fullinput += SECTION_QUERY + "\n"
    fullinput += query
    fullinput += "\n"

    if SECTION_ARGS not in inputs:
        fullinput += SECTION_ARGS + "\n"
    fullinput += inputs
    fullinput += "\n"

    # print(fullinput)
    fullinput = fullinput.encode("utf-8")

    cmd = ["node", "interpreter.js", "-"]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=fullinput,
        cwd=BINPATH,
    )
    stdout = result.stdout.decode("utf-8")
    stderr = result.stderr.decode("utf-8").strip()

    stdout = stdout.strip()
    if stdout.startswith("[") and stdout.endswith("]"):
        stdout = stdout[1:-1]
        stdout = stdout.strip()

    if not silent:
        print("-" * 80, "STDERR")
        print(stderr)
        print("-" * 80, "STDOUT")
        print(stdout)
        print("-" * 80)

    if not subresults:
        return stdout

    allresults = []
    latest_result = None
    for line in stderr.split("\n"):
        line = line.strip()
        if not line.startswith("IM_"):
            continue
        if line.startswith("IM_QUERY:"):
            if latest_result is not None:
                allresults.append(latest_result)
                latest_result = None
            latest_result = {"query": None, "args": None, "result": None}
            line = line[len("IM_QUERY:"):]
            line = json.loads(line)
            latest_result["query"] = line
        elif line.startswith("IM_ARGS:"):
            line = line[len("IM_ARGS:"):]
            line = json.loads(line)
            latest_result["args"] = line
        elif line.startswith("IM_RESULT:"):
            line = line[len("IM_RESULT:"):]
            line = json.loads(line)
            latest_result["result"] = line
    if latest_result is not None:
        allresults.append(latest_result)

    return stdout, allresults


def main():
    print("testing datalog execution")

    test_match = os.path.join(BINPATH, "test_match.dl")
    content = "\n".join(load_file(test_match))

    query = """
[:find (count ?e)
        :where [?e ":event/minute" ?minute]
        [?e ":event/type" "card"]]
        """

    inputs = []

    run_datalog(content, query, inputs)

    print("all done")


if __name__ == "__main__":
    main()
