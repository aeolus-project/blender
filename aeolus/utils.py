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


def force_repositories(input_configuration):
    """We create specification rules to force location to use the
    declared repositories. This is due to a bug in zephyrus...
    This create clauses such as:
    at{server14@aeiche.innovation.mandriva.com}(#(debian,debian_stub_package) = 1)and
    at{server21@aeiche.innovation.mandriva.com}(#(mbs,mbs_stub_package) = 1)and
    """
    clauses = []
    with open(input_configuration, 'r') as f:
        u = json.load(f)
        for l in u['locations']:
            srv_name = l['name']
            repo = l['repository']
            if repo == "mbs":
                pkg = "mbs_stub_package"
            else:
                pkg = "debian_stub_package"

            clauses.append("and at{%s}(#(%s,%s) = 1)" % (srv_name, repo, pkg))
    return clauses
