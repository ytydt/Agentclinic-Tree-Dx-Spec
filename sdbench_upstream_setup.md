# Setup guide: using SDBench/Open-MAI-Dx-Orchestrator with this project's SDBench mode

This guide explains how to install the upstream SDBench-style runtime and connect it to `SDbenchEnv`.

Repository (upstream runtime used here): https://github.com/The-Swarm-Corporation/Open-MAI-Dx-Orchestrator

> Important: In SDBench integrations, upstream APIs are usually exposed as a **gatekeeper** (ASK/TEST/DIAGNOSE) surface, not separate patient/measurement classes.  
> If you do have separate patient + measurement agents, use the `GatekeeperFacade` example in section 4 to combine them for this project's `SDbenchEnv`.

## 1) Install dependencies

```bash
# upstream package
pip install mai-dx

# this project
pip install -e .
```

If you use a source checkout for upstream:

```bash
git clone https://github.com/The-Swarm-Corporation/Open-MAI-Dx-Orchestrator.git
cd Open-MAI-Dx-Orchestrator
pip install -e .
```

## 2) Verify your upstream object shape

`SDbenchEnv` expects a gatekeeper-style object. The most common shape is:

- summary: `get_case_abstract()`
- ask: `ask(question)`
- test: `test(name)`
- diagnose: `diagnose(diagnosis)`

It also supports common alternates:

- summary: `get_initial_case_info()` or `initial_case_info`
- ask: `ask_question(question)`
- test: `order_test(name)`
- diagnose: `submit_diagnosis(diagnosis)`

## 3) Wire directly when gatekeeper methods exist

```python
from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState

gatekeeper = your_upstream_gatekeeper_object
env = SDbenchEnv(case_id="sdbench-case-1", gatekeeper=gatekeeper)

controller = AgentClinicTreeController(
    env=env,
    config=ControllerConfig(execution_mode="sdbench_patch"),
)
result = controller.run(DiagnosticState(case_id="sdbench-case-1"))
print(result)
```

## 4) If you only have separate patient + measurement agents, combine them with a facade

Use this minimal bridge so our SDBench mode can still communicate through one environment object:

```python
class GatekeeperFacade:
    def __init__(self, case_abstract: str, patient_agent, measurement_agent, diagnosis_submitter):
        self._case_abstract = case_abstract
        self.patient_agent = patient_agent
        self.measurement_agent = measurement_agent
        self.diagnosis_submitter = diagnosis_submitter

    def get_case_abstract(self):
        return self._case_abstract

    def ask(self, question: str):
        # map to your patient-agent API
        return self.patient_agent.answer(question)

    def test(self, test_name_or_panel: str):
        # map to your measurement-agent API
        return self.measurement_agent.run(test_name_or_panel)

    def diagnose(self, diagnosis: str):
        # map to your benchmark submission API
        return self.diagnosis_submitter.submit(diagnosis)
```

Then:

```python
gatekeeper = GatekeeperFacade(
    case_abstract="example case",
    patient_agent=patient_agent,
    measurement_agent=measurement_agent,
    diagnosis_submitter=diagnosis_submitter,
)
env = SDbenchEnv(case_id="sdbench-case-1", gatekeeper=gatekeeper)
```

## 5) If names differ, use callable hooks (no wrapper class required)

`SDbenchEnv` supports these gatekeeper APIs directly (or via hooks):

- Case summary:
  - `get_case_abstract()`, or
  - `get_initial_case_info()`, or
  - `initial_case_info` attribute
- Question action:
  - `ask(question)`, or
  - `ask_question(question)`
- Test action:
  - `test(name)`, or
  - `order_test(name)`
- Diagnosis submit:
  - `diagnose(diagnosis)`, or
  - `submit_diagnosis(diagnosis)`

```python
from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv

env = SDbenchEnv(
    case_id="sdbench-case-1",
    gatekeeper=your_gatekeeper_object,
    case_summary_getter=lambda gk: gk.summary_text,
    ask_fn=lambda gk, q: gk.query(q),
    test_fn=lambda gk, t: gk.run_test(t),
    diagnose_fn=lambda gk, dx: gk.finalize(dx),
)
```

## 6) Run SDBench mode

```python
from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState

env = SDbenchEnv(case_id="sdbench-case-1", gatekeeper=your_gatekeeper_object)
config = ControllerConfig(execution_mode="sdbench_patch")
controller = AgentClinicTreeController(env=env, config=config)

result = controller.run(DiagnosticState(case_id="sdbench-case-1"))
print(result)
```
