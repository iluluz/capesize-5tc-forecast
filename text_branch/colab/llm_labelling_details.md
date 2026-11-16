# LLM labelling: exact settings (for the report / README)

| Setting | Value |
|---|---|
| Model | `Qwen/Qwen2.5-7B-Instruct` (Hugging Face), released Sep 2024 → training data ends before our news window (from Aug 2025) |
| Precision | 4-bit NF4 quantization (bitsandbytes), compute in float16, free Colab T4 GPU |
| Input | headline + first 300 characters of the lead if the lead has ≥ 40 characters, else headline only; **no dates**, no question about later events |
| Decoding | **no text generation**: one forward pass per headline; we read the next-token logits for the letters A/B/C/D and apply a softmax over those 4 → probabilities. Deterministic (no sampling, so temperature does not apply; equivalent to temperature 1 over the 4 options) |
| Label | class with the highest probability (A bullish, B neutral, C bearish, D not relevant); `llm_score` = P(bullish) − P(bearish) |
| Batch / run time | batch 16; 9,512 headlines in about 2h20 (11 Nov 2026) |
| Code | `text_signal/colab/01_llm_labels.ipynb` (step 5 = prompt, step 6 = labelling) |

Label shares: see `run_summary.md` (written by notebook 02, step 6).

## Exact prompt

System message (the user message is `Text: "<headline + lead>"` followed by `Label:`; Qwen chat template, generation prompt added):

```
You label news headlines for a freight analyst. Question: if a Capesize ship owner read only this text, would they expect Capesize freight rates to go up or down over the next few weeks?
Capesize ships carry mainly iron ore (Brazil/Australia to China), coal and bauxite. Rates rise with more cargo, longer voyages or fewer available ships; they fall with less cargo, shorter voyages or more ships.
A = Bullish (rates likely up): more iron ore/coal/bauxite shipped or demanded, China stimulus or steel output up, ships rerouted on longer routes, port congestion or ships stuck, attacks or closures that slow shipping traffic or raise risk, capesize or Baltic index rising.
B = Neutral: about dry bulk or its drivers but no clear direction (mixed news, company deals, general fleet or regulation news, a tanker-only incident with no wider shipping effect).
C = Bearish (rates likely down): less iron ore/coal shipped or demanded, China steel output cuts or weak property sector, routes reopening or transits resuming, congestion easing, many new ships delivered, capesize or Baltic index falling.
D = Not relevant: nothing to do with dry bulk shipping or its cargoes (oil prices, tanker rates or container lines with no link to dry bulk, iron ore, coal or shipping routes; politics; sports; general markets).
Judge Capesize rates, not the general mood: bad news for the world can be good for freight rates. If unsure between a direction and B, answer B.
Examples:
"Baltic index hits one-week high as capesize rates surge" -> A
"Crew abandons burning tanker near Hormuz" -> A
"Iran says safe transit of Hormuz will be possible" -> C
"China orders steel output cuts to curb overcapacity" -> C
"Star Bulk announces strategic partnership with Hermes World Maritime" -> B
"Oil prices jump as OPEC+ extends supply cuts" -> D
Answer with one letter only: A, B, C or D.
```
