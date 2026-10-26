import os, json, re
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # check the Groq console for current models

SYSTEM = """You write the narrative sections of a greenhouse-gas audit summary.
Rules:
- Use ONLY numbers that appear in the JSON. Never calculate or invent values.
- Call every result an estimate; mention the status, boundary_notes and every warning.
- Say the uncertainty interval applies only to the scenario named in 'applies_to'.
- Do not claim carbon credits are issued or verified.
- Sections: Purpose, Method and boundaries, Results, Uncertainty, Limitations. Plain text.
- List every emission factor whose status is "assumed" and say it needs verification before any compliance use."""

def _nums(o, out):
    if isinstance(o, dict): [_nums(v, out) for v in o.values()]
    elif isinstance(o, (list, tuple)): [_nums(v, out) for v in o]
    elif isinstance(o, (int, float)) and not isinstance(o, bool): out.add(round(float(o), 1))
    return out

def grounded(text, payload):
    allowed = _nums(payload, set()) | {0.0, 1.0, 2.0, 95.0}
    found = {round(float(x.replace(",", "")), 1) for x in re.findall(r"\d[\d,]*\.?\d*", text)}
    return found <= allowed

def write_narrative(payload):
    resp = client.chat.completions.create(
        model=MODEL, temperature=0,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": json.dumps(payload)}])
    text = resp.choices[0].message.content
    if not grounded(text, payload):
        raise ValueError("Narrative has numbers not in the audit data")
    return text

def fallback_narrative(payload):
    g = payload["ghg"]
    return (f"Estimated baseline {g['baseline_kgco2e_d']:.1f} kgCO2e/day, proposed "
            f"{g['proposed_kgco2e_d']:.1f} kgCO2e/day, difference {g['delta_kgco2e_d']:.1f}. "
            "All values are illustrative estimates.")

def make_report(payload):
    """
    Generate an audit report using the AI narrative,
    falling back to a deterministic narrative if necessary.
    """
    try:
        narrative = write_narrative(payload)
    except Exception as exc:
        print(f"AI narrative generation failed: {exc}")
        narrative = fallback_narrative(payload)

    return {
        "status": "success",
        "report": narrative,
        "audit_data": payload,
    }