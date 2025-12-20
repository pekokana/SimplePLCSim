def parse_rung(rung_str):
    coil = rung_str.split("--(")[1].replace(")", "").strip()
    logic = rung_str.split("--(")[0].replace("[", "").replace("]", "").strip()
    logic = logic.replace("AND", "and").replace("OR", "or").replace("NOT", "not")
    return {"logic": logic, "coil": coil}
