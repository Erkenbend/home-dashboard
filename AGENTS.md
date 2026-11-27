# Rules

## Language

* Code in english (variables, function names, technical docs, ...)
* Commits in english
* User-Interface in german
* UI texts live only in the catalogs `src/home_dashboard/locales/*.toml` (`de.toml` is the reference), never as literals in templates or code
* When adding, changing or removing a UI text, update **every** catalog in the same commit, not only `de.toml`: translate the new meaning, don't just copy the German. `tests/test_language.py` catches missing keys and placeholders, but not a stale translation
* Chat in the language of the user's prompt

## Coding

* Solo development: commit directly on main unless instructed otherwise
* Commit after each meaningful step (e.g. initial plan and decisions documented, spike finished, widget implemented), don't batch unrelated steps into one commit
* Push only after the user confirms
* Report choices made autonomously, assume the user is a developer
* Focus on producing a well-testable architecture
* Test at behaviour level: prefer a slightly slower but stable integration test to a fast but brittle unit test
* Keep performance benchmarks to a minimum: only when a problem is suspected or upon request, we don't need scientific-grade precision
