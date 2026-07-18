# Crosswalk Fixup — 2026_collector
Run: 2026-07-14

## Actions
- Netflix exclusions: 11 fights (2026-05-16 non-UFC card)
- REJECT fuzzy: DOSDES, DIAPER (surname collision, different fights)
- Side assignment fix: substring normalization rule applied
  - AORHAD: Qileng Aori / Aoriqileng
  - PERMUD: Su Mudaerji / Sumudaerji
  - LEBSEO: Seok Hyun Ko / Seokhyeon Ko

## Corrected Match Rate (2026 UFC fights only)
| | N | % |
|---|---|---|
| exact | 113 | 99.1% |
| fuzzy | 0 | 0.0% |
| unmatched | 1 | 0.9% |
| UFC denominator | 114 | |
| Netflix excluded | 11 | |

## Lopes/Garcia Flip Test
MAD original: 0.161
MAD flipped:  0.003
Verdict: FLIP