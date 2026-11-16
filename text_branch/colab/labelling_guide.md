# Labelling guide: news headlines for Capesize freight rates

Used by **people** (the 100-headline check) and, word for word, as the **instructions to the LLM**, so both label by the same rules.

**Question for every headline:** *If a Capesize ship owner read only this headline (and the first paragraph, if given), would they expect Capesize freight rates to go up or down over the next few weeks?*

Capesize ships (about 180,000 tonnes) carry mainly **iron ore** (Brazil/Australia to China) and **coal**, plus bauxite (Guinea). Rates rise when there is more cargo, longer voyages or fewer available ships. They fall when there is less cargo, shorter voyages or more ships.

| Label | Meaning | Typical signals |
|---|---|---|
| **A: Bullish** | Rates likely **up** | More iron ore/coal/bauxite shipped or demanded; China stimulus or steel output up; ships rerouted on longer routes; port congestion or ships stuck (fewer ships available); attacks or closures that slow traffic or raise risk; capesize/Baltic index rising |
| **B: Neutral** | About dry bulk or its drivers, but **no clear direction** | Mixed or balanced news; company deals with no market effect; general fleet or regulation news; facts with no "more/less" |
| **C: Bearish** | Rates likely **down** | Less iron ore/coal shipped or demanded; China steel output cuts or weak property sector; routes reopening or transits resuming (ships freed up); congestion easing; many new ships delivered; capesize/Baltic index falling |
| **D: Not relevant** | **Nothing to do with dry bulk** shipping or its cargoes | Oil prices, tanker rates or container lines **with no link** to dry bulk, iron ore, coal or shipping routes; politics, sports, general markets |

## Rules

1. **Judge Capesize, not the general mood.** Bad news for the world can be good news for freight rates.
2. **Use only the text.** Don't use what you know happened later.
3. **Hormuz:** a disruption is *bullish* (risk, rerouting, ships tied up, higher costs), a reopening or safe-transit news is *bearish*. A tanker-only incident with no wider shipping effect is *neutral*.
4. **Oil and energy news is "not relevant"** unless it mentions shipping routes, bunker fuel, dry bulk, iron ore or coal.
5. **Baltic index reports:** "capesize rates rise / index gains" → bullish; "falls / slips" → bearish. These describe the market today; label them anyway.
6. **When in doubt between a direction and neutral → neutral.** When in doubt about relevance, but the headline is about shipping → neutral.

## Examples

| Headline | Label | Why |
|---|---|---|
| Baltic index hits one-week high as capesize rates surge | A Bullish | Rates rising |
| Crew abandons burning tanker near Hormuz | A Bullish | Attack raises risk and disrupts traffic (FinBERT says negative) |
| Commodity vessel transits through Strait of Hormuz fall to three-month low | A Bullish | Fewer transits, ships tied up |
| China widens BHP iron ore ban amid contract talks | B Neutral | Changes who supplies, not clearly how much is shipped |
| Star Bulk announces strategic partnership with Hermes World Maritime | B Neutral | Company news, no market direction |
| Iran says safe transit of Hormuz will be possible | C Bearish | Reopening frees up ships, risk falls (FinBERT says positive) |
| Baltic index falls to six-week low on capesize weakness | C Bearish | Rates falling |
| China orders steel output cuts to curb overcapacity | C Bearish | Less steel means less iron ore shipped |
| Oil prices jump as OPEC+ extends supply cuts | D Not relevant | Oil market, no dry bulk link |
| Tesla ends production of its Cybertruck | D Not relevant | Unrelated |
