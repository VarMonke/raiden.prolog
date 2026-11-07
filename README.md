# Markov Chain trained on Raiden Shogun, in prolog.

> Corpus is scraped from the Genshin Impact wiki and it's *small* (~6.5k
> tokens, everything she canonically says). She just doesn't have that
> many lines, so output quality is jank as hell.

Here is a stochastic process built declaratively(and Raiden Shogun obviously)

A k-th-order Markov chain over ~470 sentences of her voice lines, character stories, Serenitea Pot dialogue and birthday mails scraped from the Genshin wiki.

## Requirements

- SWI-Prolog (`brew install swi-prolog`)
- Python 3 (only needed to rebuild the corpus)

## Usage

```sh
./markov                  # 5 sentences
./markov 10               # 10 sentences
./markov "the shogun"     # talk to her, continues from your last words
./markov "the shogun" 3   # seed + sentence count
./markov I shall 2        # bare words work too
```

Chat mode:

```
$ ./markov "Hello" 2
You: Hello
Raiden Ei, Her Excellency, the Almighty Narukami Ogosho, God of Thunder: Is
that what you mean, "believing that their descendants shall witness the
same faith will form the foundations of the modern world.
```

Interactive:

```prolog
$ swipl src/markov.pl
?- stats.
order 2, 467 sentences, 7034 transitions, 4963 distinct states
?- say(3).
?- say_from(['the', 'shogun'], 3).   % seeded generation
?- order(3), say(2).                  % switch chain order, re-learns
```

## Chain order

`markov_order/1` defaults to **2** (the classic second-order chain). Higher
orders give more coherent but more parrot-like output — the corpus is only
~6.5k tokens, so by order 4 she's mostly quoting herself verbatim.

```sh
MARKOV_ORDER=3 ./markov 5   # order 3 reads best imo
```

## How it works

- `corpus.pl` holds `s([tokens]).` facts — one per sentence, punctuation
  tokenized.
- `learn/0` slides a `k+1` window over each sentence (padded with `k`
  `start` markers, terminated by `end`) and asserts every observed
  `state -> next` pair as a separate `trans(State, Next)` fact —
  duplicates kept. Sampling uniformly among matching facts reproduces the
  learned frequencies for free, no counting.
- `gen/4` walks states autoregressively, restarting at `start` markers on
  `end` or dead ends.

## Rebuilding the corpus

```sh
python3 src/build_corpus.py            # fetches wikitext via the wiki API
python3 src/build_corpus.py --cached   # offline, uses data/raw/
```

To feed her more lines: drop extra sources into `PAGES` /
`extract()` in `build_corpus.py` and rerun (she doesn't have many canon lines, which is very unfair but oh well.)

## Layout

```
markov              # ./markov shell wrapper
src/
  markov.pl         # the chain: learn, gen, cli
  corpus.pl         # generated sentence facts (git-committed for convenience)
  build_corpus.py   # wiki fetcher + tokenizer -> corpus.pl
  data/raw/         # cached API responses for --cached rebuilds
```
