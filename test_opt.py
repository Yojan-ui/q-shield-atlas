import os
from qpiai_opt.opt_modeller import Binary, Model
from qpiai_opt.opt_solvers import Client, solve

client = Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
x, y = Binary("x"), Binary("y")
m = Model("selection")
m.maximize(6*x + 4*y)
m.add_constraint(x + y <= 1, label="capacity")
r = solve(m, client=client)
print(r.problem_class, r.solution, r.objective)
