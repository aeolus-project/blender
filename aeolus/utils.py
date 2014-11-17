def get_provide_xpath(xpath):
    return "/".join(xpath.split("/")[0:3])


def get_lifecycle(xpath):
    return xpath.split("/")[0]


def get_state(xpath):
    return xpath.split("/")[1]
