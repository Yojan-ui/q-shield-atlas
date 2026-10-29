import os

from qpiai_opt.opt_modeller import Binary, Model
from qpiai_opt.opt_solvers import Client, solve
from qpiai_opt.quantum import QAOA, XYMixer
from qpiai_opt.quantum._shared import QUBOProblem
from qpiai_quantum.authentication import QpiAIQuantumAuth


def main():
    # Classical API configuration
    api_key = os.environ.get("QPIAI_OPT_API_KEY")
    client = Client(api_key=api_key) if api_key else None

    # Quantum authentication is optional for this local-simulator test.
    quantum_key = os.environ.get("QCLOUD_API_KEY")
    if quantum_key:
        QpiAIQuantumAuth.login(quantum_key)

    scores = [2, 5, 8, 4]

    # --------------------------------------------------
    # 1. Classical model
    # --------------------------------------------------
    model_class = Model("classical_demo")
    x_c = [Binary(f"algo_{i}") for i in range(4)]

    model_class.maximize(
        sum(scores[i] * x_c[i] for i in range(4))
    )
    model_class.add_constraint(
        sum(x_c) == 1,
        label="pick_one"
    )

    print("\n--- Classical Exact Solver ---")
    res_class = solve(model_class, client=client)

    print("Objective:", res_class.objective)
    print("Solution:", res_class.solution)

    # --------------------------------------------------
    # 2. Quantum model
    # The XY mixer preserves the one-hot state.
    # Convert the model explicitly to QUBO before solving.
    # --------------------------------------------------
    model_quant = Model("quantum_demo")
    x_q = [Binary(f"algo_{i}") for i in range(4)]

    model_quant.maximize(
        sum(scores[i] * x_q[i] for i in range(4))
    )

    qubo_quant = QUBOProblem.from_model(model_quant)

    qaoa_algo = QAOA(
        reps=2,
        initial_state=[1, 0, 0, 0],
        mixer=XYMixer(
            groups=[[0, 1, 2, 3]],
            topology="ring"
        )
    )

    print("\n--- Quantum QAOA Solver (Local Simulator) ---")
    print("Converted input type:", type(qubo_quant).__name__)

    res_quant = solve(
        qubo_quant,
        mode="local",
        algorithm=qaoa_algo
    )

    print("Objective:", res_quant.objective)
    print("Solution:", res_quant.solution)


if __name__ == "__main__":
    main()
