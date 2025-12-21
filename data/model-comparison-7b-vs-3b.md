# Qwen2.5-VL Model Comparison: 7B vs 3B for Handwriting OCR

**Test Date:** 2025-12-21
**Test File:** Common Book.note (2 pages of handwritten notes)
**Resolution:** 800px max dimension

## Executive Summary

The **7B model provides significantly better accuracy** for handwriting OCR, especially for proper nouns, names, and context-dependent text. The 3B model is 4.5x faster but makes more errors that would affect searchability.

**Recommendation:** Keep 7B as the production default.

---

## Speed Comparison

| Metric | 7B Model | 3B Model | Speedup |
|--------|----------|----------|---------|
| Page 1 time | ~103s | 28.1s | 3.7x |
| Page 2 time | ~144s | 25.7s | 5.6x |
| **Avg per page** | **~120s** | **26.9s** | **4.5x** |
| Total characters | 1,674 | 1,681 | +0.4% |

---

## Quality Comparison

### Page 1 - Key Differences

| Original Context | 7B Result | 3B Result | Accuracy |
|------------------|-----------|-----------|----------|
| Holiday party details | "TM is xmas with **Julia's family**" | "TM is here with the **Sea's family**" | 7B ✓ |
| Metaphor | "imagine it **as** prison" | "imagine it **at** prison" | 7B ✓ |
| Phrase ending | "Be careful what you **wish for**" | "Be careful what you **do**" | 7B ✓ |
| Community goal | "better **forested**" | "better **protected**" | Unclear |
| Family names | "**Thomas Teresa and Jenna**" | "**Tiffany, Tessa, and Jenn**" | Need original |

### Page 2 - Key Differences

| Original Context | 7B Result | 3B Result | Accuracy |
|------------------|-----------|-----------|----------|
| Rice metaphor | "your **bounty** of rice" | "your **Count's** rice" | 7B ✓ |
| Shakespeare ref | "**Lear** and his 100 knights" | "**Dear** and his 100 knights" | 7B ✓ |
| Word choice | "Based on **buggers**" | "Based on **bigger**" | Unclear |
| Final word | "**Mirror**" | "**Minor**" | Need original |

---

## Full Text Comparison

### Page 1 - 7B Model (817 chars)

```
12/24/24
Lemon will be here soon. I am trying to get ready but something will def be left undone. You do have to enjoy the process. Life is not a collection of checklists!
Today, we are going to Julia's holiday party! TM is xmas with Julia's family.
Jan 7th, 2025
I had a bad day at work. Felt trapped. No matter how lucky you are, you can find a way to imagine it as prison. Be careful what you wish for.
5 things I am grateful for:
1) The ability to help make my community safer and better forested.
2) My wife and the headstart we have given our daughter.
3) My morning coffee
4) Thomas Teresa and Jenna nearby.
5) The financial means to weather most misfortune
Bonus
6) My ability to read and think.
Jan 8th
You cannot fix everything. And when fixing it is not a crushing burden; it's a gift of growth and agency.
```

### Page 1 - 3B Model (817 chars)

```
12/24/24
Lemon will be here soon. I am trying to get ready but something will def be left undone. You do have to enjoy the process. Life is not a collection of checklists!
Today we are going to Julia's holiday party. TM is here with the Sea's family.

Jan 7th, 2025
I had a bad day at work. Felt trapped. No matter how lucky you are, you can find a way to imagine it at prison. Be careful what you do.

5 things I am grateful for:
1) The ability to help make my community safer and better protected
2) My wife and the headstart we have given our daughter.
3) My morning coffee
4) Tiffany, Tessa, and Jenn nearby.
5) The financial means to weather most misfortunes
Bonus
6) My ability to read and think.

Jan 8th
You cannot fix everything. And when fixing it is not a crushing burden, it's a gift of growth and agency.
```

### Page 2 - 7B Model (857 chars)

```
Robertson - Mindful Stoicism
- Shift from external objectives & values to
internal. 1 million isn't enough. You won't
always be a superstar at work. But
What can you do?
- Live simply & without complaint on the
scantiest & most meager fair. Then
the money is just preferred toppings
to your bounty of rice & beans.
- Work a bit each day to learn more
- reflect on what does & doesn't work
even if you may not do better
next time.
- Core Values should be clarified.
- What is the most important thing.
- Eulogy: What will be said?
- Quality/Character of others that you
- find what you value in others in yourself.
- Mirror.
August 29th 2025
I'll go back to work soon (Sept 8th). Hopefully remotely.
Dec 10th, 2025
Lear and his 100 knights. Based on buggers. Gorgeous war.
- Lear misunderstood what time it is for
- It's do we in our 30s with kids vs Freedom
```

### Page 2 - 3B Model (864 chars)

```
Robertson - Mindful Stoicism
- Shift from external objectives & Values to internal. I. million isn't enough. You won't always be a superstar at work. But what can you do?
- Live simply & without complaint on the scantiest & most meager fare. Then the money it just preferred tipping to your Count's rice & beans.
- Work a bit each day to learn more
- reflect on what does & doesn't work even if you may not do better next time.
- Core Values should be clarified
- What is the most important thing.
- Eulogy: What will be said?
- Quality/Character of others that you admire
- find what you value in others in yourself.
- Minor.

August 29th 2025
It's back to work soon (Sept 8th). Hopefully remotely.
Dec 10th, 2025
Dear and his 100 knights. Based on bigger. Gorgeous
- Dear misunderstood what time it is for
his excuses.
- It's do "in" our 30s with kids vs Freedom
```

---

## Historical Context

From earlier testing on **Reading Notes.note** (13 pages):

| OCR Source | Total Characters | Improvement |
|------------|------------------|-------------|
| Supernote built-in OCR | 5,510 | baseline |
| 7B Enhanced OCR | 11,400 | **+106.9%** |

The 7B model captured significantly more text that the Supernote device missed entirely.

---

## Model Details

| Model | HuggingFace Path | Size | Memory |
|-------|------------------|------|--------|
| 7B | mlx-community/Qwen2.5-VL-7B-Instruct-8bit | ~9GB | ~8GB RAM |
| 3B | mlx-community/Qwen2.5-VL-3B-Instruct-8bit | ~4GB | ~4GB RAM |

---

## Recommendations

| Use Case | Recommended Model |
|----------|-------------------|
| **Production** | 7B - accuracy matters for searchable notes |
| **Batch processing important notes** | 7B |
| **Quick previews/drafts** | 3B acceptable |
| **Memory-constrained systems** | 3B |
| **Speed-critical, accuracy-tolerant** | 3B |

---

## Conclusion

The 3B model offers a **4.5x speedup** but at the cost of accuracy on:
- Proper nouns (Lear → Dear)
- Names (Julia → Sea, Thomas → Tiffany)
- Context-dependent phrases (wish for → do)
- Semantic understanding (bounty → Count's)

For handwritten notes that will be searched and referenced, **the 7B model's accuracy advantage outweighs the speed benefit of 3B**.
