import json


def get_provide_xpath(xpath):
    return "/".join(xpath.split("/")[0:3])


def get_lifecycle(xpath):
    return xpath.split("/")[0]


def get_state(xpath):
    return xpath.split("/")[1]


def apply_cardinality(universe_path, cardinalities):
    # Replace cardinality of requires in universe files
    def replace(universe_json):
        # We replace the cardinality in the universe by the
        # cardinality specified in cardinalities
        for c in universe_json['component_types']:
            for s in c['states']:
                new_requires = {}
                for xpath, card in s['require'].items():
                    for c1 in cardinalities:
                        if xpath == "@"+c1['xpath']:
                            card = c1['cardinality']
                    new_requires[xpath] = card
                s['require'] = new_requires
        return universe_json

    with open(universe_path, 'r') as f:
        u = json.load(f)
        ret = replace(u)
        with open(universe_path, 'w') as f:
            json.dump(ret, f, indent=1)
