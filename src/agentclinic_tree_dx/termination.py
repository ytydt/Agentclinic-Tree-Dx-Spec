def run_termination_judge(env, state):
    return env.call_module("TerminationJudge", state)
