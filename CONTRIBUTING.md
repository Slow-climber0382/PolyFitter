# Contributing / Współpraca

Submit changes through a fork and pull request. Keep each PR focused on a concrete
user need. Describe the before/after behavior, exact changes, tests and limitations.
Run `npm test` and `npm run build`; test affected browser interactions manually.
Preserve original geometry and legacy project compatibility. Never commit personal
measurements, credentials, or third-party STL files without publication rights.

All contributions intended for inclusion are submitted under Apache-2.0 unless explicitly
stated otherwise. Keep third-party notices. Modified files in redistributed derivatives
must carry prominent modification notices under Apache-2.0 section 4(b). We recommend
also providing a human-readable change summary with your distribution.

An independent authorized maintainer must review changes before merging. Do not merge
your own PR or bypass review checks. CI is necessary but is not human review.
The owner must enable branch protection; see MAINTAINERS.md.

## Po polsku

Zgłaszaj poprawki przez fork i pull request. Opisz konkretny problem, zachowanie przed
i po zmianie, dokładny zakres, testy i ograniczenia. Uruchom `npm test`, `npm run build`
i sprawdź zmienione funkcje w przeglądarce. Nie dodawaj prywatnych pomiarów, danych
logowania ani modeli bez prawa publikacji. Zachowaj zgodność starszych projektów.

Zmiany do oficjalnego projektu wymagają przeglądu przez uprawnionego opiekuna innego
niż autor. Testy automatyczne nie zastępują recenzji. Jeśli właściciel jest jedynym
opiekunem i autorem PR, potrzebny jest drugi recenzent z odpowiednimi uprawnieniami.
