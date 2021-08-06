import sys
import os
import os.path
from glob import glob
from dataclasses import dataclass
import json
import random
import numpy as np
import pandas as pd
from string import digits

from types import SimpleNamespace

#
COREF_PROBABILITY = 0.1  # probability of a coreference
COREF_KEYS = set(["player1"])


def json_dump(obj):
    """
    Helper to output debug information on an object.
    """
    if type(obj) is pd.DataFrame:
        print("-------", obj)
        return None

    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()

    try:
        return obj.toJSON()
    except: # noqa
        try:
            return obj.__dict__
        except: # noqa
            return obj


class Ruleset:
    def __init__(self, identifier):
        self.identifier = str(identifier)
        self.filename = None
        self.rules = []

    def __repr__(self):
        return "<Ruleset '%s' (%s rules)>" % (self.identifier, len(self.rules))

    def add(self, rule):
        if rule.empty():
            return False
        if type(rule.content) is list:
            rule.content = "\n".join(map(str.rstrip, rule.content))
        self.rules.append(rule)
        return True

    def get(self, target, identifier):
        for rule in self.rules:
            rule_target = rule.get_precondition("target")
            rule_id = rule.get_precondition("id")
            if rule_id == identifier and rule_target == target:
                return rule
        return None

    def applicable(self, target, context):
        applicable_rules = []
        for rule in self.rules:
            if not rule.check(context):
                continue
            if not rule.fillers_available(context):
                continue
            applicable_rules.append(rule)
        return applicable_rules

    def targets(self):
        alltargets = set()
        for rule in self.rules:
            rule_target = rule.get_precondition("target")
            if rule_target:
                alltargets.add(rule_target)
        return alltargets

    def toJSON(self):
        return json.dumps(
            {"identifier": self.identifier, "rules": self.rules}, default=json_dump
        )

    def dumps(self):
        for idx, rule in enumerate(self.rules):
            print("#%s" % idx, rule.preconditions)
            print("\t" + ("\n\t".join(rule.content.split("\n"))).strip())

    def to_dict(self, context):
        if not type(context) is dict:
            context_d = {}
            context_keys = [
                k
                for k in dir(context)
                if not k.startswith("__")
                and not k == "dbentry"
                and not k == "clone"
                and not k == "events"
            ]

            for k in context_keys:
                kval = getattr(context, k)
                if hasattr(kval, "__call__"):
                    kval = kval()
                # print("ctxdict", k, kval, type(kval))
                context_d[k] = json.loads(json.dumps(kval, default=json_dump))

            context_d["type"] = type(context).__name__.split(".")[-1]
            context = json.loads(json.dumps(context_d, default=json_dump))
        else:
            if "type" not in context:
                context["type"] = type(context).__name__.split(".")[-1]

        return context

    def transform(
        self,
        target,
        context,
        sampling=True,
        doraise=False,
        previous_replacements=None,
        applicable_rules=None,
        return_rule=False,
        **kwargs
    ):
        context = self.to_dict(context)
        context["target"] = target

        for k, v in kwargs.items():
            context[k] = v

        if applicable_rules is None:
            applicable_rules = self.applicable(target, context)

        transformation_rule = None

        # has_coref = False
        # for rule in applicable_rules:
        #     if not rule.get_precondition("coref", None) is None:
        #         has_coref = True
        # print("applicable rules:", len(applicable_rules), "coref", has_coref)

        if len(applicable_rules) > 20:
            applicable_rules = random.sample(applicable_rules, 20)

        if len(applicable_rules) == 0:
            if doraise:
                descrip = str(type(context))
                if "type" in context:
                    descrip += " type=" + context["type"]
                if "subtype" in context:
                    descrip += " subtype=" + context["subtype"]
                print(context.keys())
                raise Exception(
                    "no applicable rules found: %s, %s"
                    % (descrip, clean_context(context))
                )

            if return_rule:
                return None, None, None
            else:
                return None, None
        elif len(applicable_rules) == 1:
            transformation_rule = applicable_rules[0]
        else:
            # if sampling:
            #    transformation_rule = random.choice(applicable_rules)
            # else:
            transformation_rule = list(applicable_rules)

        if False:
            if type(transformation_rule) is list:
                print("applicable rules (%s)" % len(transformation_rule))
                for rule in transformation_rule:
                    print("\t", rule)
            else:
                print("applicable rule: %s" % transformation_rule)
        transformed = None

        replacements = {}
        active_rule = None
        if type(transformation_rule) is list:
            if not sampling:
                all_transformed = []
                for rule in transformation_rule:
                    cur_transformed, replacements = rule.apply(
                        context, previous_replacements
                    )
                    previous_replacements = replacements
                    all_transformed.append(cur_transformed)
                    active_rule = rule  # .get_precondition("id", None)

                transformed = "\n".join(all_transformed)
            else:
                all_res = []
                for rule in transformation_rule:
                    cur_transformed, cur_replacements = rule.apply(
                        context, previous_replacements
                    )
                    active_rule = rule  # .get_precondition("id", None)
                    all_res.append([cur_transformed, cur_replacements, active_rule])
                all_res = list(
                    filter(lambda t: not t[0] is None and not t[1] is None, all_res)
                )
                # print("ALL_RES", [x[0] for x in all_res])
                transformed, replacements, active_rule = random.choice(all_res)
        else:
            transformed, replacements = transformation_rule.apply(
                context, previous_replacements
            )
            active_rule = transformation_rule
        if return_rule:
            return transformed, replacements, active_rule
        else:
            return transformed, replacements


def clean_context(context):
    exc_context = dict(context)
    if type(exc_context) is dict and "match" in exc_context:
        del exc_context["match"]
        exc_context["match"] = {"match_id": context["match"].match_id}

    return exc_context


def filter_namefilter(rule, fullpattern, obj, context):
    if obj is None:
        raise Exception(
            "rule %s: could not apply filter to null object in pattern %s\ncontext: %s"
            % (rule, fullpattern, clean_context(context))
        )

    names = []
    player_name = obj.name
    rm_digits = str.maketrans("", "", digits)
    player_name = player_name.translate(rm_digits)

    # player_num = [int(s) for s in obj.name.split() if s.isdigit()]

    names.append(player_name)
    names.append(player_name.split(" ")[-1])
    return random.choice(names)


def filter_pteam(player, data):
    if "team" not in data or data["team"] is None:
        return None
    event_team = data["team"]
    if player == 2:
        if event_team == "home":
            event_team = "away"
        else:
            event_team = "home"
    return getattr(data["match"], "%steam" % event_team)


def filter_team(whichteam, data):
    return getattr(data["match"], "%steam" % whichteam)


def filter_hometeam(rule, fullpattern, data, context):
    return filter_team("home", context)


def filter_awayteam(rule, fullpattern, data, context):
    return filter_team("away", context)


def filter_p1team(rule, fullpattern, data, context):
    return filter_pteam(1, context)


def filter_p2team(rule, fullpattern, data, context):
    return filter_pteam(2, context)


def filter_teamname(rule, fullpattern, data, context):
    return getattr(context["match"], "%steam" % data)


def filter_clean(rule, fullpattern, data, context):
    return str(data).replace("_", " ").lower().strip()


def quote(val):
    if type(val) is str:
        return '"%s"' % val
    else:
        return str(val)


def filter_dataloggenerator(rule, fullpattern, data, context):
    dl_rules = []

    if not context or context["type"] == "Match":
        res = """
            {:match/id "match_{@data.match_id}"
            :match/league "{@data.league}"
            :match/hometeam "{@data.hometeam}"
            :match/awayteam "{@data.awayteam}"
            :match/score "{@data.score}"
            :match/hometeam_goals "{@data.home_goals}"
            :match/awayteam_goals "{@data.away_goals}"}
            """.strip().split(
            "\n"
        )
        res = map(lambda line: "\t%s" % line.strip(), res)
        return "\n".join(res)
    else:

        export_keys = set(
            [
                "type",
                "subtype",
                "elapsed",
                "elapsed_plus",
                "minute",
                "sortorder",
                "team",
                "event_type",
                "goal_type",
                "card_type",
                "reason",
                "venue",
            ]
        )
        ignore_keys = set(["event_type_id", "target"])
        for k, v in context.items():
            if k == "match":
                dl_rules.append(':event/match_id "match_{@data.match.match_id}"')
            elif k == "event_id":
                dl_rules.append(':event/id "event_%s"' % context["event_id"])
            elif k == "player1":
                dl_rules.append(':event/player1 "%s"' % context["player1"].name)
            elif k == "player2":
                dl_rules.append(':event/player2 "%s"' % context["player2"].name)
            elif k in export_keys:
                dl_rules.append(":event/%s %s" % (k, quote(v)))
            elif k in ignore_keys:
                pass
            else:
                raise Exception("unhandled event key %s, val=%s" % (k, v))

        return "\n".join(map(lambda line: "\t%s" % line, dl_rules))


# [event_{@data.event_id} :event/type "{@data.type}"]
FILTERS = {
    "namefilter": filter_namefilter,
    "p1team": filter_p1team,
    "p2team": filter_p2team,
    "hometeam": filter_hometeam,
    "awayteam": filter_awayteam,
    "teamfilter": filter_teamname,
    "datalogfilter": filter_dataloggenerator,
    "clean": filter_clean,
}


@dataclass
class Rule:
    preconditions: object
    content: object

    def __init__(self, preconditions=None, content=None):
        self.preconditions = preconditions
        self.lineno = -1
        self.content = content

    def get_precondition(self, key, default_value=None):
        key == key.lower()
        if not key:
            raise Exception("no key provided")
        for k, v in self.preconditions:
            if k.startswith("@"):
                k = k[1:]
            if k.startswith("data."):
                k = k[len("data."):]
            if k.lower() == key:
                return v
        return default_value

    def empty(self):
        if not self.preconditions or not self.content:
            return True
        return False

    def toJSON(self):
        return json.dumps(
            {"preconditions": self.preconditions, "content": self.content},
            default=json_dump,
        )

    def resolve(self, context, path, verbose=False):
        if path.startswith("@"):
            path = path[1:]
        original_path = path
        if path == "data":
            return context
        path = path.split(".")
        target = context
        if len(path) > 0 and not type(target) is dict:
            target = target.__dict__

        while len(path) > 0:
            cur = path.pop(0)
            otarget = target
            if not type(target) is dict:
                target = dict(target.__dict__)
            if cur not in target:
                if cur in dir(otarget):
                    target = getattr(otarget, cur)()
                else:
                    if verbose:
                        print("not found: %s" % original_path)
                    return None
            else:
                target = target[cur]
        return target

    def fillers(self):
        allfillers = set()
        result = self.content[:]
        iterc = 0

        while result is not None and "{" in result and "}" in result:
            pstart = result.index("{")
            pend = result.index("}", pstart + 1)
            tbefore = result[:pstart]
            tafter = result[pend + 1:]
            tpattern = result[pstart + 1: pend].strip()
            if tpattern.startswith("@"):
                tpattern = tpattern[1:]

            if tpattern.lower().startswith("data."):
                tpattern = tpattern[len("data."):]
            # print("tpattern", tpattern)
            filtercall = None
            if "|" in tpattern:
                filtercall = tpattern[tpattern.index("|") + 1:].strip().lower()
                if filtercall == "":
                    filtercall = None
                tpattern = tpattern[: tpattern.index("|")]
            if filtercall is not None and filtercall == "p1team":
                allfillers.add("player1")
            if filtercall is not None and filtercall == "p2team":
                allfillers.add("player2")
            if tpattern != "":
                allfillers.add(tpattern)

            result = "%s%s" % (tbefore, tafter)
            iterc += 1

        allfillers = filter(lambda l: l is not None and not l == "", allfillers)
        return set(allfillers)

    def apply(self, context, previous_replacements):
        # print("apply", self)
        result = self.content[:]

        is_datalog = self.get_precondition("target") == "datalog"
        coref_value = self.get_precondition("coref", "")

        if coref_value is None or coref_value == "" or not coref_value:
            coref_value = None

        skip_filters = False
        restore_brackets = False
        replacements = {}

        previous_iteration = None

        while result is not None and "{" in result and "}" in result:
            pstart = result.index("{")
            pend = result.index("}")
            tbefore = result[:pstart]
            tafter = result[pend + 1:]
            tpattern = result[pstart + 1: pend].strip()
            if tpattern.startswith("@"):
                tpattern = tpattern[1:]

            if tpattern.lower().startswith("data."):
                tpattern = tpattern[len("data."):]

            # print("tpattern", tpattern)
            filtercall = None
            fullpattern = tpattern
            if "|" in tpattern:
                filtercall = tpattern[tpattern.index("|") + 1:].strip().lower()
                if filtercall == "":
                    filtercall = None
                tpattern = tpattern[: tpattern.index("|")]
            resolved = self.resolve(context, tpattern)

            # co-reference introduction
            replacements[tpattern] = str(resolved)
            if (
                previous_replacements is not None
                and tpattern in previous_replacements
                and previous_replacements[tpattern] is not None
                and replacements[tpattern] is not None
                and previous_replacements[tpattern] == replacements[tpattern]
            ):
                # was mentioned in previously generated text, coreference possible
                if tpattern in COREF_KEYS and random.random() < COREF_PROBABILITY:
                    # check if rule is compatible with co-reference replacements
                    if coref_value:
                        resolved = coref_value
                        skip_filters = True
                        replacements["coref"] = True

            if filtercall is not None and not skip_filters:
                if filtercall not in FILTERS:
                    raise Exception("undefined filter '%s'" % filtercall)

                resolved = FILTERS[filtercall](self, fullpattern, resolved, context)
                if resolved is None:
                    print(
                        "resolved is null after filter %s in rule %s"
                        % (filtercall, self)
                    )
                    result = None

            result = "%s%s%s" % (tbefore, resolved, tafter)

            if is_datalog:
                result = result.strip()
                if result.startswith("{") and result.endswith("}"):
                    restore_brackets = True
                    result = result[1:-1]

            if len(result) > 500:
                raise Exception(
                    "|res| maxlen exceeded\n%s\nwas: %s" % (result, self.content[:])
                )
            if not previous_iteration is None:
                if previous_iteration == result:
                    raise Exception("failed to resolve further:\n%s" % result)
            previous_iteration = result
        if restore_brackets:
            result = "{%s}" % result
        if "data" in replacements:
            del replacements["data"]

        if not is_datalog:
            # make sure to capitalize sentence start
            result = result[0].upper() + result[1:]

        if coref_value and not skip_filters:
            return None, replacements

        return result, replacements

    def syntax_check(self):
        try:
            condition = self.get_precondition("condition")
            if condition:
                eval(condition, {"data": {}})
            return None
        except Exception as err:
            return err

    def check_condition(self, context, condition):
        context_keys = context.keys()
        context = SimpleNamespace(**context)
        eval_globals = {}
        eval_locals = {"data": context, "keys": context_keys}
        try:
            # if context.type == 'cross' and condition == "data.type=='cross' and data.player1 and not hasattr(data, 'player2')":
            #    import pdb; pdb.set_trace()
            eval_result = eval(condition, eval_globals, eval_locals)
            return eval_result
        except Exception as caught:
            return caught

    def fillers_available(self, context):
        rule_fillers = self.fillers()

        for filler in rule_fillers:
            target_value = self.resolve(context, filler)
            if target_value is None:
                return False

        return True

    def check(self, context):
        if self.preconditions is None:
            return True

        for precon_type, precon_value in self.preconditions:
            # print(precon_type, precon_value)
            if precon_type.startswith("@"):
                precon_type = precon_type[1:]
            if precon_type.startswith("data."):
                precon_type = precon_type[len("data."):]

            # special cases first
            if precon_type == "@type":
                data_type = context["type"]
                if not type(context["type"]) is str:
                    data_type = type(context["type"]).__name__.split(".")[-1]
                if precon_value is not None:
                    if precon_value.lower() != data_type.lower():
                        return False
            elif precon_type in ["coref", "id", "category", "propagate", "answertype"]:
                continue
            elif precon_type == "condition":
                condition_result = self.check_condition(context, precon_value)
                if (
                    type(condition_result) is Exception
                    or type(condition_result) is SyntaxError
                ):
                    if "invalid syntax" in str(condition_result) or "NameError:" in str(
                        condition_result
                    ):
                        raise condition_result
                    # print("condition failed", precon_value, condition_result)
                    return False
                if not condition_result:
                    # print("condition failed", precon_value, condition_result)
                    return False
            else:
                target = self.resolve(context, precon_type)
                op_negate = False

                if type(precon_value) is str and precon_value.startswith("!"):
                    try:
                        precon_value = json.loads(precon_value[1:])
                        op_negate = True
                    except json.JSONDecodeError as jsonerr:
                        raise Exception(
                            "Failed to decode: %s, %s" % (precon_value.strip(), jsonerr)
                        )
                if type(precon_value) is str and precon_value.startswith("@"):
                    precon_value = self.resolve(context, precon_value)

                if not target:
                    return False

                if type(precon_value) is list:
                    valid = False
                    for checkval in precon_value:
                        if target == checkval:
                            valid = True
                            break

                    if not valid:
                        return False
                else:
                    if op_negate:
                        if precon_value is not None and target == precon_value:
                            return False
                    else:
                        if precon_value is not None and not target == precon_value:
                            return False

        return True


def parse_descriptor(content, lineno=-1, filename="unknown"):
    preconditions = []
    attribs = {}
    content = content.strip()

    while len(content) > 0:
        key = None
        value = None
        valueless = False

        if "=" in content and "," in content:
            if content.index(",") < content.index("="):
                valueless = True
        elif "," in content and "=" not in content:
            valueless = True
        elif "," not in content and "=" not in content:
            valueless = True

        if valueless:
            raise Exception(
                "value not found for key %s, file %s, line #%s"
                % (key, filename, lineno)
            )

        if "=" in content and not valueless:
            key = content[: content.index("=")].strip()
            content = content[content.index("=") + 1 :]

        if "," in content:
            in_expr = False
            delimpos = -1
            for idx, c in enumerate(content):
                if c == '"' and not in_expr:
                    in_expr = True
                    continue
                if c == '"' and in_expr:
                    in_expr = False
                    continue
                if c == "," and not in_expr:
                    delimpos = idx
                    break

            if delimpos > -1:
                value = content[:delimpos]
                content = content[delimpos + 1:]
            else:
                value = content
                content = ""
        else:
            value = content
            content = ""

        if value is not None:
            value = value.strip()
            if not value.startswith("@") and not value.startswith("!"):
                try:
                    value = json.loads(value.strip())
                except json.JSONDecodeError as jsonerr:
                    raise Exception(
                        "Failed to decode file %s, line #%s: %s, %s"
                        % (filename, lineno, value.strip(), jsonerr)
                    )

        if key is not None and key.startswith("="):
            key = key[1:]
            attribs[key] = value
        else:
            preconditions.append([key, value])
        content = content.strip()

    return preconditions, attribs


def load(filename, identifier="ruleset"):
    rules = Ruleset(identifier)
    rules.filename = filename
    current_rule = Rule()

    with open(filename, "rt") as infile:
        for lineidx, line in enumerate(infile):
            line = line.rstrip()
            if line.startswith("#"):
                continue

            if line == "":
                if current_rule is not None and not current_rule.empty():
                    rules.add(current_rule)
                current_rule = Rule()
                current_rule.lineno = lineidx + 1
                continue
            lstrip = line.strip()
            if current_rule.preconditions is None:
                if (
                    lstrip.startswith("[")
                    and lstrip.endswith("]")
                    and "@target" in lstrip
                ):
                    (
                        current_rule.preconditions,
                        current_rule.attributes,
                    ) = parse_descriptor(
                        lstrip[1:-1], lineno=lineidx + 1, filename=filename
                    )
            else:
                if line.startswith("\t"):
                    line = line[1:]
                if line.startswith(" " * 4):
                    line = line[4:]
                if current_rule.content is None:
                    current_rule.content = []
                current_rule.content.append(line)
    if current_rule is not None and not current_rule.empty():
        rules.add(current_rule)
    return rules


def loadall(silent=False):
    """
    Load all available transformation definitions in `./data/transformations/`.
    """
    res = {}
    for filename in glob("./data/transformations/*.transform"):
        ruleset = os.path.basename(filename).replace(".transform", "")
        res[ruleset] = load(filename, ruleset)
        print("ruleset", ruleset, len(res[ruleset].rules), "rules loaded")
        if not silent:
            print(res[ruleset].dumps())
    return res


def get_line_descriptor(ruleset, rule):
    return "%s:%s" % (ruleset.filename, rule.lineno)


def syntax_check(rulesets):
    """
    Performs a set of syntax check on the items in a given ruleset.
    """
    for ruleset_id, ruleset in rulesets.items():
        print("ruleset", ruleset_id, ruleset)
        print("targets", ruleset.targets())
        ruleset_fillers = set()

        for rule in ruleset.rules:
            if not rule.get_precondition("target"):
                print(
                    "rule %s %s does not define target"
                    % (get_line_descriptor(ruleset, rule), rule)
                )
                sys.exit(1)
            check_result = rule.syntax_check()
            if check_result is not None and (type(check_result) is SyntaxError):
                print(
                    "rule %s %s failed syntax check"
                    % (get_line_descriptor(ruleset, rule), rule)
                )
                print("condition:", rule.get_precondition("condition"))
                print("error:", check_result)
                sys.exit(2)
            for filler in rule.fillers():
                ruleset_fillers.add(filler)
        # ruleset("textrep", context=random_match, sampling=True)
        print("fillers", ruleset_fillers)


if __name__ == "__main__":
    print("loading available rulesets")
    rulesets = loadall(silent=True)
    print("performing syntax check")
    syntax_check(rulesets)
    print("all done.")
