# Setup guide: using upstream AgentClinic patient + measurement agents in this project

This guide shows how to install the upstream AgentClinic project and wire its patient and measurement agents into `AgentClinicEnv`.

## 1) Clone both repositories

```bash
git clone https://github.com/SamuelSchmidgall/AgentClinic.git
git clone <your-fork-or-local-url-of-agentclinic-tree-dx>
```

## 2) Create one shared Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
```

## 3) Install dependencies

Install upstream AgentClinic requirements first, then this project in editable mode:

```bash
pip install -r AgentClinic/requirements.txt
pip install -e ./agentclinic-tree-dx
```

## 4) Make upstream AgentClinic importable

Either run scripts from inside `AgentClinic/`, or add it to `PYTHONPATH`:

```bash
export PYTHONPATH="$PYTHONPATH:$PWD/AgentClinic"
```

## 5) Create upstream patient/measurement agents and pass them into `AgentClinicEnv`

```python
from agentclinic import ScenarioLoaderMedQA, PatientAgent, MeasurementAgent
from agentclinic_tree_dx.adapters.agentclinic_env import AgentClinicEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


class NoOpModerator:
    def review_case(self, payload):
        return {"status": "skipped", "reason": "no external moderator configured"}


# Upstream scenario + agents.
loader = ScenarioLoaderMedQA()
scenario = loader.get_scenario(id=0)
patient = PatientAgent(scenario=scenario, backend_str="gpt4o")
measurement = MeasurementAgent(scenario=scenario, backend_str="gpt4o")

env = AgentClinicEnv(
    case_id="agentclinic-medqa-0",
    initial_summary="Interactive AgentClinic case.",
    patient_agent=patient,
    tester_agent=measurement,
    moderator_agent=NoOpModerator(),  # optional
)

controller = AgentClinicTreeController(
    env=env,
    config=ControllerConfig(execution_mode="agentclinic_physician_patch"),
)

result = controller.run(DiagnosticState(case_id="agentclinic-medqa-0"))
print(result)
```

## 6) Interface compatibility expected by `AgentClinicEnv`

- Patient agent methods supported:
  - `answer_question(question)` (native adapter style), or
  - `inference_patient(question)` (upstream AgentClinic style).
- Measurement/tester agent methods supported:
  - `perform_test(test_type, request)` (native adapter style), or
  - `inference_measurement(request)` (upstream AgentClinic style).

`moderator_agent` is optional. If omitted, the final output includes:

```json
{"status":"skipped","reason":"no moderator agent configured"}
```

## 7) Notes

- Upstream AgentClinic also supports different datasets (`MedQA`, `NEJM`, etc.) via its scenario loaders and CLI configuration.
- API-key setup is handled by upstream AgentClinic runtime/model configuration (for example OpenAI/Replicate/HF model usage).
