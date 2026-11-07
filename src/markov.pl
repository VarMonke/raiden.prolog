% markov.pl
% A k-th-order Markov chain trained on Raiden Shogun text.
%
% Model: P(next | w1..wk) over tokens — autoregressive with a window of k.
% Sentences are padded with k 'start' markers and closed with 'end', so the
% chain also learns how sentences begin and how they follow each other.
% Change the order with markov_order/1 (2 = classic second-order chain;
% higher values give more coherent but more parrot-like output).
%
% Storage trick: each observed state -> next occurrence is asserted as a
% separate trans/2 fact (duplicates kept). Picking uniformly among the
% facts that match a state then samples with the learned frequencies —
% no explicit counting needed.
%
% Usage:
%   swipl markov.pl, then  say(5).
%   swipl -g "say(5),halt" markov.pl
%

:- dynamic markov_order/1.
markov_order(K) :-                   % env override: MARKOV_ORDER=3 ./markov
    getenv('MARKOV_ORDER', S),
    catch(atom_number(S, K), _, fail), !.
markov_order(2).

:- dynamic trans/2.   % trans(StateList, Next) — one fact per occurrence
:- dynamic s/1.       % s([tokens]) — corpus sentences, from corpus.pl
:- dynamic learned/0.

% Load corpus.pl relative to this file's location, not the cwd.
:- prolog_load_context(file, F),
   file_directory_name(F, D),
   atomic_list_concat([D, '/corpus.pl'], C),
   ( exists_file(C) -> consult(C)
   ; format(user_error, 'corpus.pl not found — run build_corpus.py first~n', [])).


% wow sand can think

learn :-
    retractall(trans(_, _)),
    retractall(learned),
    markov_order(K),
    forall(s(S), learn_sentence(K, S)),
    assertz(learned).

learn_sentence(K, S) :-
    start_state(K, Pad),
    append(Pad, S, S1),
    append(S1, [end], Stream),
    emit(K, Stream).

% slide a k+1 window; each step asserts state -> next
emit(K, Stream) :-
    length(Stream, L),
    L > K,
    length(State, K),
    append(State, [C | _], Stream),
    assertz(trans(State, C)),
    Stream = [_ | Tail],
    emit(K, Tail).
emit(_, _).

ensure_learned :-
    ( learned -> true ; learn ).

% order(K) — change chain order at runtime and re-learn (try order(3))
order(K) :-
    retractall(markov_order(_)),
    assertz(markov_order(K)),
    learn.

% generatowor

% start_state(K, State) — K copies of the start marker
start_state(K, State) :- length(State, K), maplist(=(start), State).

start_state(State) :- markov_order(K), start_state(K, State).

% shift a token into the state window
push(State, W, State1) :-
    State = [_ | Mid],
    append(Mid, [W], State1).

% generate(+NSentences, -Tokens)
generate(N, Tokens) :-
    start_state(S0),
    gen(S0, N, 300, Tokens).

gen(_, 0, _, []) :- !.
gen(_, _, 0, []) :- !.
gen(State, S, Fuel, Out) :-
    findall(C, trans(State, C), Cs),
    (   Cs == []
    ->  % dead end: restart from a sentence boundary (give up if already there)
        start_state(Empty),
        (   State == Empty
        ->  Out = []
        ;   gen(Empty, S, Fuel, Out)
        )
    ;   random_member(Next, Cs),
        (   Next == end
        ->  S1 is S - 1,
            start_state(Empty),
            gen(Empty, S1, Fuel, Out)
        ;   Out = [Next | More],
            push(State, Next, State1),
            Fuel1 is Fuel - 1,
            gen(State1, S, Fuel1, More)
        )
    ).

random_member(X, Xs) :-
    length(Xs, L),
    I is random(L),
    nth0(I, Xs, X).

no_space_before(',').
no_space_before('.').
no_space_before('!').
no_space_before('?').
no_space_before(';').
no_space_before(':').
no_space_before('...').
no_space_before(')').
no_space_before(']').

no_space_after('(').
no_space_after('[').

join(Tokens, Text) :-
    join_(Tokens, none, false, Parts),
    atomics_to_string(Parts, Text).

% join_(+Tokens, +Prev, +InsideQuote, -Parts) — emits separator+token pairs.
% InsideQuote tracks " parity: an opening " glues forward, a closing " glues back.
join_([], _, _, []).
join_([T | Ts], Prev, Open, [Sep, T | Rest]) :-
    (   Prev == none -> Sep = ''
    ;   glue(Prev, T, Open) -> Sep = ''
    ;   Sep = ' ' ),
    (   T == '"' -> neg(Open, Open1)
    ;   Open1 = Open ),
    join_(Ts, T, Open1, Rest).

neg(false, true).
neg(true, false).

glue(_, Cur, _) :-
    Cur \= '"', no_space_before(Cur), !.
glue(Prev, '"', Open) :-
    !, (Open -> true ; no_space_after(Prev)).
glue('"', _, Open) :-
    !, Open.                    % word right after an opening quote glues to it
glue(Prev, _, _) :-
    no_space_after(Prev).


say(N) :-
    ensure_learned,
    generate(N, Tokens),
    join(Tokens, Text),
    format('~w~n', [Text]).

say :- say(5).

% because swipl is weird
% Entry point for `swipl markov.pl -- args` (the ./markov wrapper).
% Interactive loads and -g runs see an empty argv and skip this.
:- initialization(run_cli, main).

run_cli :-
    current_prolog_flag(argv, Argv),
    (   Argv == []
    ->  true
    ;   cli(Argv), halt ).

% markov [seed words...] [sentence-count]   (count defaults to 5)
cli(Argv) :-
    ensure_learned,
    (   append(SeedArgs, [NA], Argv), atom_number(NA, N), integer(N)
    ->  true
    ;   SeedArgs = Argv, N = 5 ),
    seed_words(SeedArgs, Seed),
    state_of(Seed, S0),
    gen(S0, N, 300, Tokens),
    join(Tokens, Text),
    (   Seed == []
    ->  format('~w~n', [Text])
    ;   atomic_list_concat(Seed, ' ', YouText),
        format('You: ~w~n~s: ~w~n',
               [YouText,
                "Raiden Ei, Her Excellency, the Almighty Narukami Ogosho, God of Thunder",
                Text]) ).

% argv atoms -> flat token list ("the shogun" or the shogun both work)
seed_words(Args, Words) :-
    maplist(atom_string, Args, Strs),
    atomic_list_concat(Strs, ' ', Joined),
    split_string(Joined, " \t", " \t", Parts),
    maplist(atom_string, Words0, Parts),
    exclude(==(''), Words0, Words).

% seed -> starting state: the last k words, left-padded with start markers
state_of(Words, State) :-
    markov_order(K),
    length(Words, L),
    (   L >= K
    ->  length(State, K),
        append(_, State, Words)
    ;   P is K - L,
        start_state(P, Pad),
        append(Pad, Words, State) ).

% generate N sentences continuing from a seed — for interactive use
say_from(Seed, N) :-
    ensure_learned,
    state_of(Seed, S0),
    gen(S0, N, 300, Tokens),
    join(Tokens, Text),
    format('~w~n', [Text]).

stats :-
    ensure_learned,
    markov_order(K),
    aggregate_all(count, trans(_, _), Trans),
    aggregate_all(count, s(_), Sents),
    findall(St, trans(St, _), Pairs),
    sort(Pairs, Uniq),
    length(Uniq, States),
    format('order ~d, ~d sentences, ~d transitions, ~d distinct states~n',
           [K, Sents, Trans, States]).
