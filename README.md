# VA claims agent

A CS329Z project. A multi-agent system helps a law firm take on a veteran's VA disability claim:
from the first chat message, through signing and filing the power of attorney (VA Form 21-22a)
and the fee agreement, to a one-page case summary (the "face note") that an attorney reviews.

- **Agents:** an orchestrator hands each case to sub-agents: **intake** (screening, documents,
  filing), **claims prep** (reads the veteran's VA claims file, the "C-file", and writes the face
  note) and **customer support**. Every agent runs on Claude Haiku 5.5 through OpenRouter.
- **Simulated:** VA, filing, the eFax and the attorney.
- **Synthetic data only:** every veteran, C-file and number in this repo is made up.

How it is built (architecture, guards, design decisions): [docs/DESIGN.md](docs/DESIGN.md).

This README has two parts:
- **[Part 1: no key, no cost](#part-1-no-key-no-cost)**: the scripted demo and the recorded eval results.
- **[Part 2: live runs](#part-2-live-runs-needs-an-openrouter-key)**: the live demo and rerunning
  the eval, with an OpenRouter key.

## Install

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/lukasa1/Allard_Liu.git
cd Allard_Liu
uv sync                 # creates .venv and installs everything from uv.lock
uv run pytest -q        # optional check: ~550 tests, about 2 minutes, no key and no network
```

# Part 1: no key, no cost

## 1. The scripted demo

The demo is a web page with two halves:
- **Left: what the veteran sees.** You play the veteran: the chat, with cards for the secure
  form, document previews, the signature and Sign.
- **Right: the firm's internal side.** Tabs: Attorney (you countersign here), Case, Answers, Face
  note, Event log.

The page plays one synthetic veteran, Hector Alvarez. Above the chat, **You are playing…** lists
his facts, so you know what to answer.

```bash
uv run intake serve --scripted
```

1. Open http://localhost:8000 and press **Start case**.
2. The chat box holds the veteran's next line from the recorded run: press **Enter** to send it.
3. Use each card as it appears:
   - **secure form:** its test values are already filled in; press **Submit securely**;
   - **signature:** draw it, or press **Type** to type your name;
   - **Sign:** click it.
4. When the Attorney tab says **waiting for you**, press **Countersign both documents**.
5. The documents are then filed, and claims prep reads the C-file. Keep pressing Enter
   through the last questions.
6. The case ends at **stage 5, ready for attorney review**. The **Face note** tab shows the
   result, each line with the C-file page it came from.

The agents replay one recorded eval run (`recent_decision` in `results/midpoint`) word for word: every
model output comes from that run, so the box takes only the run's next line. Everything else (tools,
guards, documents, PDFs, the face-note verifier) is the real code.

## 2. The eval results

The eval runs **synthetic veterans** ("personas", in `agent/data/personas/`) through whole cases on
the live system. An LLM plays each veteran from a hidden answer key, the app clicks its cards, and
the final case file is scored against the key. A second eval sends 84 labelled messages to the
customer-support agent.

The midpoint run's results are in the repo:
- **`results/midpoint/report.md`** has the tables:
  - the headline, with field accuracy, critical errors and scenario pass;
  - a section per agent;
  - **By split**: `dev` = the 14 personas the system was developed against, `heldout` = 6 not fixed
    against directly (both are optimistic);
  - every case's critical errors and field mismatches.
- `results/midpoint/summary.json` holds the same numbers as data.
- `results/midpoint/transcripts/` holds every conversation.
- `results/support-midpoint/summary.json` and `misses.txt` hold the support numbers and the misses.

`uv run intake personas` lists the 20 personas.

# Part 2: live runs (needs an OpenRouter key)

## 3. Set the API key

1. Create a key at https://openrouter.ai/keys. It needs a few dollars of credit.
2. Copy the example file and paste the key in:

   ```bash
   cp .env.example .env
   # edit .env:  OPENROUTER_API_KEY=sk-or-...
   ```

`.env` is gitignored. Every other setting in `.env.example` (model, data folder) has a working
default and can stay commented out.

## 4. The live demo (about $0.20 per case)

```bash
uv run intake serve
```

The same page and steps as [the scripted demo](#1-the-scripted-demo), but the agents are the live
model, so you can type anything:
- ask a question in the middle ("What is an intent to file?");
- give a wrong answer and correct it;
- reject the document preview and say what's wrong.

The grey suggestion in the chat box is written by the eval's simulated veteran (Tab takes it).
Live replies take about 5 to 15 seconds.

## 5. Rerun the eval

```bash
uv run intake eval --conditions cfile --name midpoint --max-cost 6
uv run intake support-eval --name support-midpoint --max-cost 1.5
```

| Command | What it does | Cost / time |
|---|---|---|
| `intake eval …` | All 20 personas, condition `cfile` (the full system: verification questions, plus answers prefilled from the C-file) | about $3–4, 1.5–2 h |
| `intake support-eval …` | 84 labelled messages to the customer-support agent (`--core`: the 50-message core set) | about $0.5–1, 10 min |

`--max-cost` stops the run if the traced spend passes that many US dollars. The results go where
[section 2](#2-the-eval-results) describes; a run with the same `--name` overwrites the recorded ones.

**Smaller runs:**

```bash
uv run intake simulate --persona recent_decision --max-cost 1   # one case, printed as it runs
uv run intake eval --personas baseline_clean,crisis_disclosure --conditions cfile --name try --max-cost 1
uv run intake eval --name ablation --max-cost 20                # all 3 conditions (ask_no_probes, ask, cfile)
```

**About repeating runs:**
- **Same code, same command: replayed for free.** Every case runs on a fixed clock with seeded
  IDs, so DSPy's response cache (`~/.dspy_cache`) answers a repeat at no cost, in minutes.
- **A fresh sample:** set `DSPY_CACHE=0`, or use `--trials 3` (this also gives pass^k).
- **On a clean machine:** the model is sampled anew, so the numbers vary a little from run to run.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The page says to set `OPENROUTER_API_KEY` | Add the key to `.env` (section 3) and restart the server, or use `--scripted` |
| `Address already in use` | `uv run intake serve --port 8001` |
| The signature pad doesn't draw | The page loads it from a CDN, so check the internet connection; you can still press **Type** |
| A live reply says "having trouble" | The model gave an unusable answer twice; send the message again |
| `--max-cost` is refused | The model in `DSPY_MODEL` has no price in `agent/config.py` (`PRICES`); add one, or leave the default model |
| You want to start the data over | Delete `.data/` (cases, the encrypted vault, PDFs). It is recreated on the next run |

The code map is at the end of [docs/DESIGN.md](docs/DESIGN.md#code-map).
