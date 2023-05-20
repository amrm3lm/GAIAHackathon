import dbm

DBM_STORE = "dbm_store"

def dbm_put(k,v):
    with dbm.open(DBM_STORE, 'c') as db:
        db[k] = v

def dbm_put_reviews(k,reviews,votes:list):
    v_string = [str(v) for v in votes]
    full = "///".join(reviews) + "@@@" + "]]]".join(v_string)
    with dbm.open(DBM_STORE, 'c') as db:
        db[k] = full
    print(f"put {k} into db")

def dbm_get_reviews(k):
    with dbm.open(DBM_STORE, 'c') as db:
        if k in db:
            print(f"found {k} in store")
            res = db[k].decode("utf-8")
        else:
            res = None

    if res == None:
        return None, None

    s = res.split("@@@")
    reviews = s[0].split("///")
    votes = s[1].split("]]]")
    v_num = [int(v) for v in votes]
    return reviews, v_num


def dbm_get(k):
    with dbm.open(DBM_STORE, 'c') as db:
        if k in db:
            res = db[k].decode("utf-8")
        else:
            res = None

    return res

def dbm_clean():
    with dbm.open(DBM_STORE, 'c') as db:
        for key in list(db):
            del db[key]


def tests():
    dbm_put('test', 'wow')
    print(dbm_get('test'))

    dbm_put('t2', "///".join(['wow','wowoww']))
    print(dbm_get('t2'))

    dbm_put_reviews("t3", ["first comment.", "second comment", "yes love this product!"], [1,4,66])

    print(dbm_get_reviews("t3"))

    print(dbm_get_reviews("nonex"))
    print(dbm_get_reviews("B0727WCBL7"))